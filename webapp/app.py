import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Optional

import aiohttp
from fastapi import Cookie, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from cookidoo_api import Cookidoo, CookidooConfig
from cookidoo_api.const import ADD_CUSTOM_RECIPE_PATH
from cookidoo_api.exceptions import CookidooAuthException, CookidooRequestException


def to_iso_duration(hours: int, minutes: int) -> str:
    """Convierte horas y minutos a duración ISO 8601 (ej: PT1H30M)."""
    if hours == 0 and minutes == 0:
        return "PT0S"
    parts = "PT"
    if hours:
        parts += f"{hours}H"
    if minutes:
        parts += f"{minutes}M"
    return parts

# session_id -> {"api": Cookidoo, "http_session": aiohttp.ClientSession}
user_sessions: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for s in user_sessions.values():
        await s["http_session"].close()


BASE_DIR = Path(__file__).parent

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def get_session(session_id: Optional[str]) -> Optional[dict]:
    if session_id and session_id in user_sessions:
        return user_sessions[session_id]
    return None


# ── Login ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    http_session = aiohttp.ClientSession()
    cfg = CookidooConfig(email=email, password=password)
    api = Cookidoo(http_session, cfg)

    try:
        await api.login()
    except (CookidooAuthException, CookidooRequestException) as e:
        await http_session.close()
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": f"Login fallido: {e}"}
        )

    session_id = str(uuid.uuid4())
    user_sessions[session_id] = {"api": api, "http_session": http_session}

    response = RedirectResponse("/dashboard", status_code=302)
    response.set_cookie("session_id", session_id)
    return response


@app.get("/logout")
async def logout(session_id: Optional[str] = Cookie(None)):
    if session_id and session_id in user_sessions:
        await user_sessions[session_id]["http_session"].close()
        del user_sessions[session_id]
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("session_id")
    return response


# ── Dashboard: lista de colecciones ───────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, session_id: Optional[str] = Cookie(None)):
    sess = get_session(session_id)
    if not sess:
        return RedirectResponse("/")

    api: Cookidoo = sess["api"]
    user = await api.get_user_info()
    collections = await api.get_custom_collections()

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "collections": collections, "msg": request.query_params.get("msg")},
    )


# ── Crear nueva colección ──────────────────────────────────────────────────────

@app.post("/collections/new")
async def new_collection(
    request: Request,
    name: str = Form(...),
    session_id: Optional[str] = Cookie(None),
):
    sess = get_session(session_id)
    if not sess:
        return RedirectResponse("/")

    api: Cookidoo = sess["api"]
    try:
        await api.add_custom_collection(name)
        msg = f"Coleccion '{name}' creada correctamente"
    except CookidooRequestException as e:
        msg = f"Error al crear coleccion: {e}"

    return RedirectResponse(f"/dashboard?msg={msg}", status_code=302)


# ── Detalle de colección ───────────────────────────────────────────────────────

@app.get("/collections/{collection_id}", response_class=HTMLResponse)
async def collection_detail(
    request: Request,
    collection_id: str,
    session_id: Optional[str] = Cookie(None),
):
    sess = get_session(session_id)
    if not sess:
        return RedirectResponse("/")

    api: Cookidoo = sess["api"]
    collections = await api.get_custom_collections()
    collection = next((c for c in collections if c.id == collection_id), None)

    if not collection:
        return RedirectResponse("/dashboard")

    return templates.TemplateResponse(
        "collection.html",
        {
            "request": request,
            "collection": collection,
            "msg": request.query_params.get("msg"),
            "error": request.query_params.get("error"),
        },
    )


# ── Añadir receta a colección por ID ──────────────────────────────────────────

@app.post("/collections/{collection_id}/add-recipe")
async def add_recipe_to_collection(
    request: Request,
    collection_id: str,
    recipe_id: str = Form(...),
    session_id: Optional[str] = Cookie(None),
):
    sess = get_session(session_id)
    if not sess:
        return RedirectResponse("/")

    api: Cookidoo = sess["api"]
    # El usuario introduce solo el número; si ya tiene la 'r' delante la respetamos
    rid = recipe_id.strip()
    if not rid.startswith("r"):
        rid = f"r{rid}"

    try:
        await api.add_recipes_to_custom_collection(collection_id, [rid])
        return RedirectResponse(
            f"/collections/{collection_id}?msg=Receta+{rid}+anadida+correctamente",
            status_code=302,
        )
    except CookidooRequestException as e:
        return RedirectResponse(
            f"/collections/{collection_id}?error=Error+al+anadir+receta:+{e}",
            status_code=302,
        )


# ── Crear receta personalizada desde receta oficial ───────────────────────────

@app.post("/collections/{collection_id}/create-custom")
async def create_custom_recipe(
    request: Request,
    collection_id: str,
    base_recipe_id: str = Form(...),
    serving_size: int = Form(4),
    session_id: Optional[str] = Cookie(None),
):
    sess = get_session(session_id)
    if not sess:
        return RedirectResponse("/")

    api: Cookidoo = sess["api"]
    rid = base_recipe_id.strip()
    if not rid.startswith("r"):
        rid = f"r{rid}"

    try:
        custom = await api.add_custom_recipe_from(rid, serving_size)
        msg = f"Receta+personalizada+'{custom.name}'+creada+(ID:+{custom.id})"
        return RedirectResponse(f"/collections/{collection_id}?msg={msg}", status_code=302)
    except CookidooRequestException as e:
        return RedirectResponse(
            f"/collections/{collection_id}?error=Error+al+crear+receta:+{e}",
            status_code=302,
        )


# ── Nueva receta personalizada desde cero ─────────────────────────────────────

@app.get("/recipes/new", response_class=HTMLResponse)
async def new_recipe_form(request: Request, session_id: Optional[str] = Cookie(None)):
    sess = get_session(session_id)
    if not sess:
        return RedirectResponse("/")
    return templates.TemplateResponse(
        "new_recipe.html", {"request": request, "error": request.query_params.get("error")}
    )


@app.post("/recipes/new")
async def new_recipe_submit(
    request: Request,
    titulo: str = Form(...),
    raciones: int = Form(...),
    prep_horas: int = Form(0),
    prep_minutos: int = Form(0),
    total_horas: int = Form(0),
    total_minutos: int = Form(0),
    ingredientes: Annotated[list[str], Form()] = [],
    pasos: Annotated[list[str], Form()] = [],
    session_id: Optional[str] = Cookie(None),
):
    sess = get_session(session_id)
    if not sess:
        return RedirectResponse("/")

    api: Cookidoo = sess["api"]

    # Filtrar vacíos
    ingredientes = [i.strip() for i in ingredientes if i.strip()]
    pasos = [p.strip() for p in pasos if p.strip()]

    prep_seg = (prep_horas * 3600) + (prep_minutos * 60)
    total_seg = (total_horas * 3600) + (total_minutos * 60)
    cook_seg = max(0, total_seg - prep_seg)

    base_url = api.api_endpoint / ADD_CUSTOM_RECIPE_PATH.format(**api._cfg.localization.__dict__)
    try:
        # Paso 1: crear stub con nombre y raciones
        async with api._session.post(
            base_url, headers=api._api_headers,
            json={"recipeName": titulo, "servingSize": raciones}
        ) as r:
            if r.status == 401:
                return RedirectResponse("/recipes/new?error=Sesion+expirada")
            r.raise_for_status()
            data = await r.json()
            recipe_id = data["recipeId"]

        # Paso 2: PATCH con contenido completo
        patch_url = api.api_endpoint / f"created-recipes/{recipe_id}"
        patch_body = {
            "name": titulo,
            "image": None,
            "isImageOwnedByUser": False,
            "tools": ["TM6"],
            "yield": {"value": raciones, "unitText": "portion"},
            "prepTime": prep_seg or None,
            "cookTime": cook_seg or None,
            "totalTime": total_seg or None,
            "ingredients": [{"type": "INGREDIENT", "text": i} for i in ingredientes],
            "instructions": [{"type": "STEP", "text": p} for p in pasos],
            "hints": None,
            "workStatus": "PRIVATE",
            "recipeMetadata": {"requiresAnnotationsCheck": False},
        }
        async with api._session.patch(
            patch_url, headers=api._api_headers, json=patch_body
        ) as r:
            r.raise_for_status()

        return RedirectResponse(f"/dashboard?msg=Receta+creada+correctamente", status_code=302)
    except Exception as e:
        return RedirectResponse(f"/recipes/new?error=Error+al+crear+receta:+{e}", status_code=302)


# ── Eliminar receta de colección ───────────────────────────────────────────────

@app.post("/collections/{collection_id}/remove-recipe")
async def remove_recipe_from_collection(
    request: Request,
    collection_id: str,
    recipe_id: str = Form(...),
    session_id: Optional[str] = Cookie(None),
):
    sess = get_session(session_id)
    if not sess:
        return RedirectResponse("/")

    api: Cookidoo = sess["api"]
    try:
        await api.remove_recipe_from_custom_collection(collection_id, recipe_id)
        return RedirectResponse(
            f"/collections/{collection_id}?msg=Receta+eliminada+correctamente",
            status_code=302,
        )
    except CookidooRequestException as e:
        return RedirectResponse(
            f"/collections/{collection_id}?error=Error+al+eliminar:+{e}",
            status_code=302,
        )


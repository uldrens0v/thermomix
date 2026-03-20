import uuid
from contextlib import asynccontextmanager
from typing import Optional

import aiohttp
from fastapi import Cookie, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from cookidoo_api import Cookidoo, CookidooConfig
from cookidoo_api.exceptions import CookidooAuthException, CookidooRequestException

# session_id -> {"api": Cookidoo, "http_session": aiohttp.ClientSession}
user_sessions: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    for s in user_sessions.values():
        await s["http_session"].close()


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


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

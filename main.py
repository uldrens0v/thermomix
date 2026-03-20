import asyncio
import os
import aiohttp
from dotenv import load_dotenv
from cookidoo_api import Cookidoo, CookidooConfig

load_dotenv()

async def test():
    async with aiohttp.ClientSession() as session:
        cfg = CookidooConfig(
            email=os.getenv("COOKIDOO_EMAIL"),
            password=os.getenv("COOKIDOO_PASSWORD"),
        )
        api = Cookidoo(session, cfg)

        await api.login()
        print("Login correcto")

        user = await api.get_user_info()
        print(f"Usuario: {user.username}")


        collections = await api.get_custom_collections()
        dieta = next((c for c in collections if c.name == "DIETA ANDRES"), None)

        if dieta:
            # Añadir receta oficial Mac and Cheese vegano (r792539)
            updated = await api.add_recipes_to_custom_collection(dieta.id, ["r792539"])
            print(f"Receta anadida a '{dieta.name}' correctamente")
            print(f"Recetas en la coleccion:")
            for chapter in updated.chapters:
                for r in chapter.recipes:
                    print(f"  - [{r.id}] {r.name}")
        else:
            print("No se encontro la coleccion 'DIETA ANDRES'")

asyncio.run(test())
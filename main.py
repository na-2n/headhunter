import os
import time
import json
import traceback
import sqlite3 # TODO cache username -> uuid results

from base64 import b64decode
from io import BytesIO
from time import time

from aiohttp import web, ClientSession
from aiohttp.web import middleware
from aiohttp.web_exceptions import HTTPNotFound
from multidict import MultiDict
from PIL import Image


UUID_BY_NAME = 'https://api.mojang.com/users/profiles/minecraft/'
PROFILE_BY_UUID = 'https://sessionserver.mojang.com/session/minecraft/profile/'

# in seconds (24h = 24*60*60)
MAX_CACHE_TIME = 24 * 60 * 60
PORT = 7885

fallback_head = b''

async def get_head(session, uuid):
    try:
        stati = os.stat(f'./cache/{uuid}.png')

        if stati.st_mtime + MAX_CACHE_TIME > time():
            #print('returning cached head')

            with open(f'./cache/{uuid}.png', 'rb') as f:
                return f.read()
    except:
        pass

    async with session.get(PROFILE_BY_UUID + uuid) as res:
        jsono = await res.json()

        props = jsono['properties']
        if len(props) == 0:
            raise Exception("no props")

        tex = [x['value'] for x in props if x['name'] == 'textures']
        if len(tex) == 0:
            raise Exception("no tex")
        tex = tex[0]

        data = json.loads(b64decode(tex))
        url = data['textures']['SKIN']['url']

        async with session.get(url) as res2:
            img_buf = BytesIO(await res2.read())
            buf = BytesIO()

            img = Image.open(img_buf, formats=('png',))
            img.crop((8, 8, 16, 16)).save(buf, format='png')

            with open(f'./cache/{uuid}.png', 'wb') as f:
                f.write(buf.getbuffer())

            return buf.getbuffer()

async def get_head_name(req):
    name = req.match_info.get('name', None)
    if name is None:
        raise Exception("no name")

    async with req.app['client_session'].get(UUID_BY_NAME + name) as res:
        jsono = await res.json()

        uuid = jsono.get('id', None)
        if uuid is None:
            raise Exception("no uuid")

        head = await get_head(req.app['client_session'], uuid)

        return web.Response(body=head,
                            content_type='image/png',
                            headers=MultiDict(
                                {'CONTENT-DISPOSITION': f'inline; filename="{uuid}.png"'}))

async def get_head_uuid(req):
    uuid = req.match_info.get('name', None)
    if uuid is None:
        raise Exception("no uuid")

    head = await get_head(req.app['client_session'], uuid)
    return web.Response(body=head,
                        content_type='image/png',
                        headers=MultiDict(
                            {'CONTENT-DISPOSITION': f'inline; filename="{uuid}.png"'}))

@middleware
async def err_middleware(req, handler):
    try:
        return await handler(req)
    except HTTPNotFound:
        return web.Response(status=404, body='not found')
    except:
        print(traceback.format_exc())

        return web.Response(body=fallback_head,
                            content_type='image/png',
                            headers=MultiDict(
                                {'CONTENT-DISPOSITION': f'inline; filename="fallback.png"'}))

async def client_session_ctx(app):
    app['client_session'] = ClientSession()

    yield

    await app['client_session'].close()

app = web.Application(middlewares=[err_middleware])
app.add_routes([web.get('/head/uuid/{uuid}.png', get_head_uuid),
                web.get('/head/uuid/{uuid}', get_head_uuid),
                web.get('/head/name/{name}.png', get_head_name),
                web.get('/head/name/{name}', get_head_name)])
app.cleanup_ctx.append(client_session_ctx)

if __name__ == '__main__':
    with open('./fallback.png', 'rb') as f:
        fallback_head = f.read()

    web.run_app(app, port=os.getenv('HH_PORT', PORT))


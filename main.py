import os
import json
import asyncio  # for running multiple servers
from base64 import b64encode   # for palworld admin password encoding
from typing import TypedDict, List, Optional, Any, Dict
import aiohttp  # for asynchronous HTTP requests
import uvicorn  # for fastapi server
from enum import Enum   # for server presets
from datetime import datetime   # for webhook log and embed timestamp
from dotenv import load_dotenv
from fastapi import FastAPI, Request
import discord
from discord import app_commands
from discord.app_commands import Choice

#===== environment variables =====#
load_dotenv()
discord_token = os.getenv('DISCORD_TOKEN')
server_address = os.getenv('SERVER_ADDRESS')
guild_id = int(os.getenv('GUILD_ID'))
test_guild = discord.Object(id=guild_id)
palserver_password = os.getenv('PALWORLD_ADMIN_PASSWORD')
#===== discord client variables =====#
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
#===== fastapi server variables for game server state webhook =====#
app = FastAPI()
FASTAPI_LOG_FILE = "test.json"

#===== types of json data ======#
class EmbedAuthor(TypedDict):
    name: str
    url: Optional[str]
    icon_url: Optional[str]
class EmbedFooter(TypedDict):
    text: str
    icon_url: Optional[str]
class EmbedField(TypedDict):
    name: str
    value: str
    inline: bool
class EmbedData(TypedDict):
    color: Optional[int]
    author: Optional[EmbedAuthor]
    title: str          # required
    description: str    # required
    fields: Optional[List[EmbedField]]
    thumbnail: Optional[str]
    image: Optional[str]
    video: Optional[str]
    footer: Optional[EmbedFooter]
    timestamp: Optional[str]
class EmbedEntry(TypedDict):
    guild_id: Optional[int]
    channel_id: Optional[int]
    message_id: Optional[int]
    preset: ServerPreset    # required
    alias: str              # required
    embed: EmbedData

#===== external functions =====#
async def _json_write(data: dict, filename: str):
    _data = []
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            try:
                _data = json.load(f)
            except:
                _data = []
    _data.append(data)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(_data, f, indent=4, ensure_ascii=False)
    return

async def _json_get(filename: str, *fields: str, **filters: Any) -> List[Dict[str, Any]]:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
    except:
        data = []
    return [d for d in data if all(d.get(field, None) == value for field, value in filters.items())]

async def _api_get(url: str, headers: dict):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                return
            return await response.json()
        
async def _update_player_list(data: dict):
    auth = b64encode(('admin:'+palserver_password).encode()).decode()
    url = "http://172.30.1.100:8212/v1/api/players" # get player list
    headers = {
        'Accept': 'application/json',
        'Authorization': 'Basic '+auth
    }
    # palworld argument contains various state information
    # If argument data contains player joined or left,
    # get player list and update embed
    if data.get("embeds", [{}])[0].get("title", "") in ["Player Joined", "Player Left"]:
        _text = ""     # initialize text variable to store player names
        _embed = ""
        _api_reponse = await _api_get(url, headers)
        _players = _api_reponse.get('players', [])
        if _players:
            if len(_players) > 10:
                for p in _players[:10]:
                    _text += p.get("name") + "\n"
                _text += f"외 {len(_players) - 10}명"
            else:
                _text += "\n".join([p.get("name") for p in _players])
        else:
            _text = "현재 접속 중인 플레이어가 없습니다."
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
                message_id = config.get('message_id')
                channel_id = config.get('channel_id')
                if channel_id and message_id:
                    target_channel = client.get_channel(channel_id)
                    if target_channel:
                        try:
                            message = await target_channel.fetch_message(message_id)
                            _embed = message.embeds[0] if message.embeds else discord.Embed() ## 나중에 임베드 커스터마이징 할 때 수정
                            _embed.description = _text
                            await message.edit(embed=_embed)
                            print(f"Updated player list in channel {target_channel.name}")
                        except Exception as e:
                            print(f"Error fetching or editing message: {e}")
                    else:
                        print("지정된 채널을 찾을 수 없습니다.")
                else:
                    print("config.json 파일에 channel_id 또는 message_id가 없습니다.")
        except Exception as e:
            print(f"Error reading config.json: {e}")
            #await interaction.response.send_message(
            #   f'{target_channel.mention} 채널에 메세지가 전송되었습니다.', ephemeral=True)
        else:
            pass
            print("지정된 공지 채널을 찾을 수 없습니다.")
            #
    else:
        print("API 서버에 연결할 수 없습니다.")
        pass

async def _log_webhook(game_name: str, data: dict, show_terminal=True):
    # terminal log
    if show_terminal:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {game_name.upper()}")
        print(json.dumps(data, indent=4, ensure_ascii=False))
        print(f"{'='*50}\n")
    # save log to file
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "game": game_name,
        **data
    }
    logs = []
    if os.path.exists(FASTAPI_LOG_FILE):
        with open(FASTAPI_LOG_FILE, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
            except:
                logs = []
    logs.append(log_entry)
    with open(FASTAPI_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=4, ensure_ascii=False)

@app.post("/webhook/{guild_id}/{test}")
async def _debug_webhook(game_name: str, request: Request):
    # Parse JSON payload
    try:
        data = await request.json()
    except Exception:
        return {"status": "error", "message": "Invalid JSON"}
    await _log_webhook('test', data, show_terminal=True)
    if data:
        await _update_player_list(data)
    return {"status": "success"}

#============= 봇 준비 이벤트 =============#
@client.event
async def on_ready():
    try:
        synced = await tree.sync(guild=test_guild)
        print(f"Synced {len(synced)} command(s)")
        print(f'logged in as {client.user}')
    except Exception as e:
        print(f"Error occurred while syncing application commands: {e}")
    else:
        pass

#============= 메세지 전송 채널 설정 =============# 
class ServerPreset(Enum):
    NONE = "None"
    PAL_DOCKER = "thijsvanloef/palworld-server-docker"
    COREKPR_DOCKER = "escaping/core-keeper-dedicated"
    MC_DOCKER = "itzg/minecraft-server"

@tree.command(
        name='new_embed',
        description='새 임베드를 설정합니다.',
        guild=test_guild
        )
@app_commands.describe(
    server='사용 중인 서버 프리셋 선택',
    alias='식별을 위한 임베드 별칭 입력'
    )
@app_commands.choices(fruits=[
    Choice(name='none', value=ServerPreset.NONE),
    Choice(name='[Palworld] docker dedicated server', value=ServerPreset.PAL_DOCKER),
    Choice(name='[Core Keeper] docker dedicated server', value=ServerPreset.COREKPR_DOCKER),
    ]
)

#@app_commands.checks.has_permissions(administrator=True)
async def new_embed(
    interaction: discord.Interaction,
    server: ServerPreset,
    alias: str,
    ):
    if ServerPreset.NONE == server:
        _embed = discord.Embed()
        _embed.title = alias
        _embed.description = "**Hello**, This is description"
        _embed.timestamp = datetime.now()
        _embed.set_footer(text="UnaBot")
        _embed.set_thumbnail(url="https://cdn.discordapp.com/avatars/1270023902956883980/c6d7991609a016bddba1f38fe8727eb3.webp?size=480")
        _embed.set_image(url="https://raw.githubusercontent.com/akasmb/akasmb/main/placeholder.png")
        _myembed = await interaction.channel.send(embed=_embed)
        await _json_write(
            {
                "guild_id": interaction.guild.id,
                "channel_id": interaction.channel.id,
                "message_id": _myembed.id,
                "preset": str(server),
                "alias": alias,
                "embed": {
                    "title": alias,
                    "description": "**Hello**, This is description",
                    "timestamp": _myembed.timestamp.isoformat(),
                    "footer": {
                        "text": "UnaBot"
                    },
                    "thumbnail": {
                        "url": "https://cdn.discordapp.com/avatars/1270023902956883980/c6d7991609a016bddba1f38fe8727eb3.webp?size=480"
                    },
                    "image": {
                        "url": "https://raw.githubusercontent.com/akasmb/akasmb/main/placeholder.png"
                    }
                }
            },
            "config.json"
        )
        await interaction.response.send_message(
        f'[{alias}](@{server.value}) 임베드를 생성하였습니다.',
        ephemeral=True)


# run with webserver
async def run_servers():
    config = uvicorn.Config(app, host="0.0.0.0", port=8213, loop="asyncio")
    server = uvicorn.Server(config)
    await asyncio.gather(
        client.start(discord_token),
        server.serve()
    )

if __name__ == "__main__":
    try:
        asyncio.run(run_servers())
    except KeyboardInterrupt:
        print("Shutting down...")

# run discord.client only
#client.run(discord_token)
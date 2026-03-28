from datetime import datetime
import os
import json
from enum import Enum
import asyncio
from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI, Request
import aiohttp
import discord
from discord import app_commands

load_dotenv()
discord_token = os.getenv('DISCORD_TOKEN')
server_address = os.getenv('SERVER_ADDRESS')
guild_id = int(os.getenv('GUILD_ID'))
test_guild = discord.Object(id=guild_id)
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
app = FastAPI()
FASTAPI_LOG_FILE = "webhook_log.json"

async def update_player_list(data: dict):
    url = "http://172.30.1.100:8212/v1/api/players"
    headers = {
        'Accept': 'application/json',
        'Authorization': 'Basic YWRtaW46MTIzNA=='
    }
    # initialize text variable to store player names
    # Make an asynchronous HTTP GET request to the API endpoint
    if data.get("embeds", [{}])[0].get("title", "") in ["Player Joined", "Player Left"]:
        text = ""
        embed = ""
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    _players = data.get('players', [])
                    if _players:
                        if len(_players) > 10:
                            for p in _players[:10]:
                                text += p.get("name") + "\n"
                            text += f"...외 {len(_players) - 10}명"
                        else:
                            text += "\n".join([p.get("name") for p in _players])
                    else:
                        text = "현재 접속 중인 플레이어가 없습니다."
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
                                        embed = message.embeds[0] if message.embeds else discord.Embed() ## 나중에 임베드 커스터마이징 할 때 수정
                                        embed.description = text
                                        await message.edit(embed=embed)
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
                        #print("지정된 공지 채널을 찾을 수 없습니다.")
                        #
                else:
                    #print("API 서버에 연결할 수 없습니다.")
                    pass

async def log_webhook(game_name: str, data: dict, show_terminal=True):
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

@app.post("/webhook/{game_name}")
async def debug_webhook(game_name: str, request: Request):
    # Parse JSON payload
    try:
        data = await request.json()
    except Exception:
        return {"status": "error", "message": "Invalid JSON"}
    await log_webhook(game_name, data, show_terminal=True)
    if data:
        await update_player_list(data)
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
    
#============= ㅋ =============# 
class ServerPreset(Enum):
    Pal_docker = "thijsvanloef/palworld-server-docker"
#============= 메세지 전송 채널 설정 =============# 
@tree.command(
        name='new_embed',
        description='새 임베드를 설정합니다.',
        guild=test_guild
        )
@app_commands.describe(channel='채널 선택')
#@app_commands.checks.has_permissions(administrator=True)
async def new_embed(
    interaction: discord.Interaction,
    server: str,
    alias: str,
    ):
    embed = discord.Embed(title="New Embed")
    myembed = await interaction.channel.send(embed=embed)
    myembed_id = myembed.id
    json.dump({'channel_id': interaction.channel.id, 'message_id': myembed_id}, open('config.json', 'w', encoding='utf-8'))
    await interaction.response.send_message(
    f'{channel.mention} 채널에 임베드를 생성하였습니다.', ephemeral=True)

#============= 접속 플레이어 확인 =============# 
'''
@tree.command(
        name='players',
        description='현재 서버에 접속한 플레이어 목록을 표시합니다.',
        guild=test_guild
        )
async def players(interaction: discord.Interaction):
'''

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
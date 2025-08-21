import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re
import uuid
from dotenv import load_dotenv
from discord.ui import View, Button

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "notify_words.json"

# 判定モードを日本語で表示
MODE_LABELS = {
    "p": "部分一致",
    "e": "完全一致",
    "r": "正規表現"
}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

class RemoveNotificationView(View):
    def __init__(self, user_id, channel_id, notif_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.channel_id = channel_id
        self.notif_id = notif_id

        self.add_item(Button(label="この通知を解除する", style=discord.ButtonStyle.danger, custom_id=f"remove_{user_id}_{channel_id}_{notif_id}"))

# ユーザーがサーバーを脱退またはキックされた場合
@client.event
async def on_member_remove(member: discord.Member):
    user_id = str(member.id)
    guild_id = str(member.guild.id)

    data = load_data()
    if user_id in data and guild_id in data[user_id]:
        del data[user_id][guild_id]
        save_data(data)
        print(f"[INFO] {member} が {member.guild.name} を脱退したため通知を削除しました。")

# ユーザーがBANされた場合
@client.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    user_id = str(user.id)
    guild_id = str(guild.id)

    data = load_data()
    if user_id in data and guild_id in data[user_id]:
        del data[user_id][guild_id]
        save_data(data)
        print(f"[INFO] {user} が {guild.name} からBANされたため通知を削除しました。")


@client.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.data and interaction.data["custom_id"].startswith("remove_"):
        _, user_id, channel_id, notif_id = interaction.data["custom_id"].split("_")
        user_id = int(user_id)
        channel_id = int(channel_id)

        # JSONから削除
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if str(channel_id) in data and str(user_id) in data[str(channel_id)]:
            words = data[str(channel_id)][str(user_id)]
            new_words = [w for w in words if w["id"] != notif_id]
            data[str(channel_id)][str(user_id)] = new_words

            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            await interaction.response.send_message("✅ 通知を解除しました。", ephemeral=True)

# メッセージとembedをまとめて検索用テキストに変換
def extract_message_content(message: discord.Message):
    contents = [message.content]
    for embed in message.embeds:
        if embed.title:
            contents.append(embed.title)
        if embed.description:
            contents.append(embed.description)
        for field in embed.fields:
            contents.append(f"{field.name}: {field.value}")
        if embed.footer and embed.footer.text:
            contents.append(embed.footer.text)
    return "\n".join(contents)

@client.event
async def on_ready():
    print(f"ログイン成功: {client.user}")
    try:
        synced = await client.tree.sync()
        print(f"スラッシュコマンド同期: {len(synced)}件")
    except Exception as e:
        print(e)

@client.tree.command(name="notify", description="通知ワードの操作を行います")
@app_commands.describe(
    action="add:登録, remove:削除, list:一覧",
    word="登録するワード(または正規表現)",
    mode="登録時のみ、判定方法[デフォルト: 部分一致] (p:部分一致, e:完全一致, r:正規表現)",
    target_id="削除するID (allで全削除)"
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="追加(add)", value="add"),
        app_commands.Choice(name="削除(remove)", value="remove"),
        app_commands.Choice(name="一覧(list)", value="list")
    ],
    mode=[
        app_commands.Choice(name="部分一致(Partial match)", value="p"),
        app_commands.Choice(name="完全一致(Exact match)", value="e"),
        app_commands.Choice(name="正規表現(Regular expression)", value="r")
    ]
)
async def notify(interaction: discord.Interaction, action: str, word: str = None, mode: str = "p", target_id: str = None):
    user_id = str(interaction.user.id)
    channel_id = str(interaction.channel.id)
    data = load_data()
    data.setdefault(channel_id, {}).setdefault(user_id, [])

    if action == "add":
        if any(entry["word"] == word and entry["mode"] == mode for entry in data[channel_id][user_id]):
            await interaction.response.send_message("❌ そのワードは既に登録されています。", ephemeral=True)
            return
        if word == "" or word == None:
            await interaction.response.send_message("❌ 登録ワードが空です。", ephemeral=True)
        new_id = uuid.uuid4().hex[:8]
        data[channel_id][user_id].append({"id": new_id, "word": word, "mode": mode})
        save_data(data)
        await interaction.response.send_message(f"✅ 登録しました！\nID: {new_id}, ワード: `{word}`, モード: {MODE_LABELS[mode]}", ephemeral=True)

    elif action == "remove":
        if target_id == "all":
            data[channel_id][user_id] = []
            save_data(data)
            await interaction.response.send_message("🗑️ 全ての登録ワードを削除しました。", ephemeral=True)
            return
        before = len(data[channel_id][user_id])
        data[channel_id][user_id] = [entry for entry in data[channel_id][user_id] if entry["id"] != target_id]
        after = len(data[channel_id][user_id])
        save_data(data)
        if before == after:
            await interaction.response.send_message("❌ 指定されたIDが見つかりませんでした。", ephemeral=True)
        else:
            await interaction.response.send_message(f"🗑️ ID `{target_id}` を削除しました。", ephemeral=True)

    elif action == "list":
        if not data[channel_id][user_id]:
            await interaction.response.send_message("📭 登録ワードはありません。", ephemeral=True)
        else:
            text = "\n".join([f"ID: {entry['id']} | `{entry['word']}` | モード: {MODE_LABELS[entry['mode']]}" for entry in data[channel_id][user_id]])
            await interaction.response.send_message(f"📋 登録ワード一覧:\n{text}", ephemeral=True)

@client.event
async def on_message(message: discord.Message):
    if message.author.bot and message.author.id == 1407306626368802836:
        return
    channel_id = str(message.channel.id)
    data = load_data()
    if channel_id not in data:
        return

    full_text = extract_message_content(message)

    for user_id, entries in data[channel_id].items():
        user = await client.fetch_user(int(user_id))
        for entry in entries:
            word = entry["word"]
            mode = entry["mode"]
            id = entry["id"]
            matched = False
            if mode == "p" and word in full_text:
                matched = True
            elif mode == "e" and word == full_text:
                matched = True
            elif mode == "r" and re.search(word, full_text):
                matched = True

            if matched:
                embed_list = message.embeds if message.embeds else None
                embed_dm = discord.Embed(
                    title="🔔 通知",
                    description=f"チャンネル <#{channel_id}> で `{word}` が検出されました！\n\n"
                                f"👤 送信者: {message.author.mention}\n"
                                f"💬 メッセージ: {message.content if message.content else '(本文なし)'}\n"
                                f"⚙️ 判定モード: {MODE_LABELS[mode]}"
                                f"{"\n埋め込みメッセージがあります"if embed_list else ""}",
                    color=discord.Color.orange()
                )
                try:
                    view = RemoveNotificationView(user.id, message.channel.id, id)
                    await user.send(embed=embed_dm,view=view)
                    if embed_list:
                        for emb in embed_list:
                            await user.send(embed=emb)
                except discord.Forbidden:
                    print(f"⚠️ {user} にDMを送信できませんでした。")

client.run(os.getenv("DISCORD_BOT_TOKEN"))

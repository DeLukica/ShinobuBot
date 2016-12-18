import discord
from Shinobu.client import Shinobu
from Shinobu.annotations import *
import resources
import glob
import os
import re
import json
import time
from urllib.request import urlopen
import asyncio
from math import floor
from Shinobu.utility import ConfigManager
import connector_db.highlevel as database

version = "1.2.7"



async def accept_message(message:discord.Message):
    reset_channel_timeout(message.channel.id)

def cleanup():
    global prune_loop
    if hasattr(prune_loop, "cancel"):
        print("Stopping prune loop")
        prune_loop.cancel()


async def prune_temp_channels():
    global warned_channels

    while 1:
        old_channels = get_expired_channels(600)
        for channel in old_channels:
            channel_id = str(channel["ChannelID"])
            print(channel)
            if channel_id not in warned_channels:
                await shinobu.send_message(shinobu.get_channel(channel_id), "This channel will soon be be pruned due to inactivity")
                author_id = channel["ChannelCreator"]
                print(author_id)
                user = discord.User(id=author_id)
                await shinobu.send_message(user, "<#{}> will soon be deleted due to activity.".format(channel_id))
                warned_channels.append(channel_id)
            else:
                print("Deleting channel {}".format(channel_id))
                delete_channel(channel_id)
                await shinobu.delete_channel(shinobu.get_channel(channel_id))
                warned_channels.remove(channel_id)
        await asyncio.sleep(600)



def accept_shinobu_instance(instance):
    global shinobu, prune_loop, database, votes, temp_channels
    shinobu = instance
    prune_loop = shinobu.invoke(prune_temp_channels())
    database = shinobu.get_module("connector_db")
    database.assure_table("Reichlist", (
        "ItemID SERIAL",
        "ItemContributor BIGINT UNSIGNED",
        "ItemValue VARCHAR(2000)",
        "PRIMARY KEY(ItemID)"
        ,))
    votes = database.DatabaseDict("Votes")

    database.assure_table("CreatedChannels", (
        "ChannelID BIGINT",
        "ChannelCreator BIGINT UNSIGNED",
        "ChannelLastMessage BIGINT UNSIGNED",
        "PRIMARY KEY(ChannelID)"
        ,))





def reset_channel_timeout(channelid):
    update_channel(channelid)
    global warned_channels
    if channelid in warned_channels:
        shinobu.invoke(shinobu.send_message(shinobu.get_channel(channelid), "This channel will not be deleted."))
        warned_channels.remove(channelid)


shinobu = None  # type: Shinobu
votes = None  # type: database.DatabaseDict
warned_channels = []
Description = "General commands that do not fit into a specific module."
type = "Module"


config = ConfigManager("resources/ShinobuCommands.json")
config.assure("temp_channels", [])
config.assure("check_frequency", 600)
config.assure("prune_after_seconds", 3600*24)
config.assure("warn_time", 600)

prune_loop = None # type: asyncio.futures.Future
database = None



def register_commands(ShinobuCommand):


    @ShinobuCommand
    @permissions("Shinobu Owner")
    async def broadcast(message:discord.Message, arguments:str):
        if not shinobu.author_is_owner(message):
            return
        for channel in shinobu.get_all_channels():
            if channel.is_default:
                await shinobu.send_message(channel, arguments)

    @ShinobuCommand
    @permissions("@everyone")
    @blacklist("shitpost-central")
    @description("Posts a message to any channel, even ones that a user cannot see.")
    @usage(".tell the-holodeck What do you think you are doing in there?")
    async def tell(message:discord.Message, arguments:str):
        originating_server = message.server
        given_message = arguments.rsplit(" ")[1:]
        requested_channel = arguments.rsplit(" ")[0]
        sender = message.author.id
        for channel in message.server.channels:
            if channel.name == requested_channel:
                await shinobu.send_message(channel, ("<@"+sender + "> told me to say:\n") + " ".join(given_message), tts=True)
                await shinobu.send_message(message.channel, "Sent message to {}".format(channel.name))
                return
        await shinobu.send_message(message.channel, "Could not find channel {}".format(requested_channel))

    @ShinobuCommand
    @description("Lists all the visible and hidden channels on the server and what type of channel they are.")
    async def channels(message: discord.Message, arguments: str):
        output = "**Channels on this server:**\n__Text__\n"
        for channel in message.server.channels:
            if channel.type is discord.ChannelType.text:
                output += (channel.name + "\n")
        output += "\n__Voice__\n"
        for channel in message.server.channels:
            if channel.type is discord.ChannelType.voice:
                output += (channel.name + "\n")
        await shinobu.send_message(message.channel, output)

    @ShinobuCommand
    @description("Says what system Shinobu is running on")
    @blacklist("shitpost-central")
    async def who(message: discord.Message, arguments: str):
        await shinobu.send_message(message.channel, "*Tuturu!* Shinobu desu.\n[{0}]".format(shinobu.config["instance name"]))

    @ShinobuCommand
    @description("Posts the link to the documentation on Github")
    @blacklist("shitpost-central")
    async def docs(message: discord.Message, arguments: str):
        await shinobu.send_message(message.channel, "Documentation is located at:\nhttps://github.com/3jackdaws/ShinobuBot/wiki/Full-Command-List")

    @ShinobuCommand
    @description("Bans mentioned users")
    @permissions("Shinobu Owner")
    async def ban(message: discord.Message, arguments: str):
        for member in message.mentions:
            shinobu.invoke(shinobu.ban(member, delete_message_days=0))

    @ShinobuCommand
    @description("Kicks mentioned users")
    @permissions("Shinobu Owner")
    async def kick(message: discord.Message, arguments: str):
        if not shinobu.author_is_owner(message): return
        member_id = re.search("[0-9]+", message.content).group()
        print(member_id)
        for member in shinobu.get_all_members():
            if member.id == member_id:
                print("Kicking ",member.name)
                shinobu.invoke(shinobu.kick(member))

    @ShinobuCommand
    @description("Posts current weather in klamath falls. Doesn't work on Enyo.")
    async def weather(message: discord.Message, arguments: str):
        got_json = False
        while not got_json:
            url = "http://api.wunderground.com/api/{}/geolookup/conditions/q/OR/Klamath_Falls.json".format(shinobu.config['wu_token'])
            site_text = urlopen(url).read().decode("utf-8")
            kf_json = json.loads(site_text)
            try:
                weath = kf_json["current_observation"]["weather"]
                temp = kf_json["current_observation"]["temp_f"]
                got_json = True

                emoji = ""
                if "rain" in weath.lower():
                    emoji = ":cloud_rain:"
                elif "overcast" in weath.lower():
                    emoji = ":cloud:"
                elif "clear" in weath.lower():
                    emoji = ":cityscape:"
                elif "sunny" in weath.lower():
                    emoji = ":sunny:"
                await shinobu.send_message(message.channel, "**Klamath Falls, OR**\n{0} {1} {0}\n{2}°F".format(emoji, weath, round(temp)))
            except:
                pass

    @ShinobuCommand
    @description("Purges messages from the mentioned person up until the given message id.")
    @usage(".purge @everyone 43892742837734")
    @permissions("Shinobu Owner")
    async def purge(message: discord.Message, arguments: str):
        if shinobu.author_is_owner(message):
            args = arguments.rsplit()
            print("Purging")
            channel = message.channel
            who = args[0]
            ref = args[1]
            if who == "@everyone":
                def is_after(m):
                    return m.id > args[1]
            else:
                try:
                    who = message.mentions[0]
                except:
                    await shinobu.send_message(message.channel, "The second parameter must be a mention or everyone.")
                    return
                def is_after(m):
                    user = message.mentions[0]
                    return user == m.author and m.id > ref

            num_del = len(await shinobu.purge_from(channel, check=is_after))
            mes = await shinobu.send_message(message.channel, "Deleted {} messages.".format(num_del))
            await asyncio.sleep(2)
            await shinobu.delete_message(mes)





    @ShinobuCommand
    @usage(".temp channel_name @mentions_who_can_join")
    @description("Creates a temporary channel that is removed after a day of inactivity.  The channel is only visible to the author and those that are mentioned.")
    async def temp_channel(message: discord.Message, arguments: str):
        global temp_channels
        server = message.server
        args = arguments.rsplit()
        everyone_perms = discord.PermissionOverwrite(read_messages=False)
        member_perms = discord.PermissionOverwrite(read_messages=True, manage_channels=True)
        everyone = discord.ChannelPermissions(target=server.default_role, overwrite=everyone_perms)

        access = [discord.ChannelPermissions(target=message.author, overwrite=member_perms), everyone]
        for person in message.mentions:
            access.append(discord.ChannelPermissions(target=person, overwrite=member_perms))
        channel = await shinobu.create_channel(server, args[0], *access)
        await shinobu.edit_channel(channel, topic="Temporary channel")
        expires = int(time.time()) + int(config["prune_after_seconds"])

        insert_temp_channel(channel.id, message.author.id)





    def rl_add_item(user_id, text):
        sql = "INSERT INTO Reichlist (ItemContributor, ItemValue) VALUES (%s,%s)"
        database.execute(sql, (user_id, text,))

    @ShinobuCommand
    @description("Adds a text entry to the reichlist or shows the entire reichlist.")
    @usage("[.reichlist add \"People doing thing that I hate.\"]", "[.reichlist show]")
    async def reichlist(message: discord.Message, arguments: str):
        try:
            args = arguments.rsplit(" ")
            subcommand = args[0]
            if subcommand == "add":
                text = re.findall("\"[^\"^\n]+\"", arguments)
                for item in text:
                    rl_add_item(message.author.id, item)
                await shinobu.send_message(message.channel, "Added {} entries.".format(len(text)))
            elif subcommand == "show":
                output = ""
                sql = "SELECT * FROM Reichlist ORDER BY ItemID"
                cursor = database.execute(sql) #type: pymysql.cursor
                for item in cursor.fetchall():
                    output += "{} - <@{}>\n\n".format(item["ItemValue"], item['ItemContributor'])
                await shinobu.send_message(message.channel, output)
        except:
            pass

    @ShinobuCommand
    @description("Used for voting. Subcommands are [start, for, show]")
    @usage("[.vote start \"Choice One\" \"Choice Two\" \"Choice Three\"]", "[.vote for 1]", "[.vote conclude]")
    async def vote(message: discord.Message, arguments: str):
        subcommand = arguments.rsplit()[0]
        if subcommand == "start":
            choices = re.findall("\"[^\"^\n]+\"", arguments)


def insert_temp_channel(channel_id, channel_creator_id):
    print("Create channel")
    sql = "INSERT INTO CreatedChannels (ChannelID, ChannelCreator, ChannelLastMessage) VALUES(%s, %s, %s)"
    database.execute(sql, (channel_id, channel_creator_id, str(int(time.time()))), show_errors=True)

def update_channel(channel_id):
    print("Reset channel")
    sql = "UPDATE CreatedChannels SET ChannelLastMessage=%s WHERE ChannelID=%s"
    database.execute(sql, (int(time.time()), channel_id), show_errors=True)

def delete_channel(channel_id):
    sql = "DELETE FROM CreatedChannels WHERE ChannelID=%s"
    database.execute(sql, (channel_id))


def get_expired_channels(time_since_last_message):
    sql = "SELECT ChannelID, ChannelCreator, (%s - ChannelLastMessage) as SinceLastMessage FROM CreatedChannels WHERE %s - ChannelLastMessage > %s"
    now = int(time.time())
    cursor = database.execute(sql, ( now, now, time_since_last_message))
    channels = cursor.fetchall()
    if channels:
        return channels
    else:
        return []
import os
import random
from datetime import date
import discord
from discord import app_commands
from discord.ext import commands
import dotenv

dotenv.load_dotenv()


#Wichtige Daten-------------------------------------------------------------
Server_IP=""
# Standard-Intents reichen für Slash-Commands-------------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
#alle channels--------------------------------------------------------------
#für Teamposts
TEAM_CHANNEL_ID = 1282374978645393480
#für reports
MOD_CHANNEL_ID=1483513901034373315

#wichtige dictionaries
#zählt wie oft wer ein ticket erstellt hat
ticket_zaehler={}


#für die Teamanmeldung-------------------------------------------------------
class Anmeldung(discord.ui.Modal, title="Anmeldung - max 4.Spieler"):
    teamname=discord.ui.TextInput(
        label="Teamname",
        placeholder="z.B. Die Orangen",
        max_length=32,
    )
    Leader = discord.ui.TextInput(label="Leader", max_length=32,)
    name2=discord.ui.TextInput(label="Player2", max_length=32,required=False,)
    name3=discord.ui.TextInput(label="Player3", max_length=32,required=False,)
    name4=discord.ui.TextInput(label="Player4", max_length=32,required=False,)

    async def on_submit(self, interaction: discord.Interaction):
        # wird ausgeführt, wenn jemand auf "Absenden" klickt
        await interaction.response.send_message(f"Angemeldet: {self.teamname.value}",ephemeral=True)
        felder = [self.Leader, self.name2, self.name3, self.name4]
        spieler = []

        for feld in felder:
            name = feld.value.strip()
            if name != "":
                spieler.append(name)
        await postteam(self.teamname.value, spieler)

class Report(discord.ui.Modal, title="Regelverstoß melden (max. 2 pro Tag)"):
    betreff=discord.ui.TextInput(
        label="betreff",
        max_length=32
        )
    problem=discord.ui.TextInput(
        label="problem",max_length=1000
        )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        heute=date.today()
        name=interaction.user.name
        datum, anzahl = ticket_zaehler.get(user_id, (heute, 0))
        if datum != heute:
            anzahl = 0
        if anzahl<2:
            ticket_zaehler[user_id]=(heute,anzahl+1)
            await send_report(self.betreff.value,self.problem.value,name,heute)
            await interaction.response.send_message("Danke, dein Report wurde gesendet!", ephemeral=True)
        else:
            await interaction.response.send_message("Du hast heute schon 2 Reports geschrieben.", ephemeral=True)
@bot.event
async def setup_hook():
    # Registriert die Slash-Commands bei Discord
    await bot.tree.sync()


@bot.event
async def on_ready():
    print(f"Eingeloggt als {bot.user}")


#Funktionen die keine Commands sind-----------------------------------------------------

#sendet das team mit teamnamen in den Teamchannel
async def postteam(teamname, spieler):
    channel = bot.get_channel(TEAM_CHANNEL_ID)
    if channel is None:
        print("Team-Channel nicht gefunden!")
        return
    text=""
    for name in range(1,len(spieler)):
        text+="\n**Spieler "+ str(name+1)+ "**: "+str(spieler[name])
    await channel.send(f"Team: **{teamname}**\n**Anführer**: {spieler[0]}{text}")


#sendet den report in den Modchannel
async def send_report(betreff,problem,name,heute):
    channel=bot.get_channel(MOD_CHANNEL_ID)
    if channel is None:
            print("Team-Channel nicht gefunden!")
            return
    await channel.send(f"**{name}** hat mit folgendem Betreff: **{betreff}** am {heute} folgendes Problem:\n{problem}")
    return


#Commands für den Bot-----------------------------------------------------------
@bot.tree.command(name="teamanmeldung", description="assigns teams together")
async def teamanmeldung(interaction:discord.Interaction):
        await interaction.response.send_modal(Anmeldung())
        return

@bot.tree.command(name="report", description="Was ist das Problem?")
async def report(interaction:discord.Interaction):
        await interaction.response.send_modal(Report())
        return

@bot.tree.command(name="parlaiment",description="was ist das parlament eigentlich?")
async def parlaiment(interaction:discord.Interaction):
    await interaction.response.send_message(f"",ephemeral=True)

#Commands zur Server Ip-----------------------------------------------------
@app_commands.default_permissions(administrator=True)
@bot.tree.command(name="setip",description="die Ip für den Server ändern")
async def change_ip(interaction:discord.Interaction,ip:str):
    global Server_IP
    Server_IP=ip
    await interaction.response.send_message(f"Server-IP ist jetzt: `{Server_IP}`", ephemeral=True)
    return


@bot.tree.command(name="ip", description="bekomme die server IP")
async def ip(interaction:discord.Interaction):
    await interaction.response.send_message(Server_IP,ephemeral=True)
    return


#Alle Forms Commands--------------------------------------------------------------

@bot.tree.command(name="report", description="Was ist das Problem?")
async def report(interaction:discord.Interaction):
        await interaction.response.send_modal(Report())
        return


@bot.tree.command(name="hallo", description="Sagt hallo")
async def hallo(interaction: discord.Interaction):
    await interaction.response.send_message(f"Hey {interaction.user.mention}! 👋")


bot.run(os.environ["DISCORD_TOKEN"])
import os
import random
from datetime import date
import discord
from discord import app_commands
from discord.ext import commands
import dotenv
import json
from mcrcon import MCRcon, MCRconException
dotenv.load_dotenv()

#Wichtige Daten-------------------------------------------------------------
Server_IP = "not set"
RCON_HOST = "localhost"   # IP vom PC, auf dem der Minecraft-Server läuft
RCON_PORT = 25575
# Intents: members wird gebraucht, damit get_member_named funktioniert------
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
#alle channels--------------------------------------------------------------
#für Teamposts
TEAM_CHANNEL_ID = 1282374978645393480
#für mods
MOD_CHANNEL_ID = 1483513901034373315
#für wissen welche spieler am server sind
#ACHTUNG: aktuell dieselbe ID wie MOD_CHANNEL_ID, ggf. anpassen
PLAYER_CHANNEL_ID = 1483513901034373315

TEAM_CATEGORY_ID = None


#wichtige dictionaries------------------------------------------------------
#zählt wie oft wer ein ticket erstellt hat
ticket_zaehler = {}


#flags----------------------------------------------------------------------
whitelist_flag = True


#Hilfsfunktionen für die spieler.json---------------------------------------
def lade_spieler():
    try:
        with open("spieler.json", "r") as datei:
            return json.load(datei)
    except FileNotFoundError:
        return {}


def speichere_spieler(daten):
    with open("spieler.json", "w") as datei:
        json.dump(daten, datei, ensure_ascii=False, indent=4)

def lade_teams():
    try:
        with open("teams.json", "r") as datei:
            return json.load(datei)
    except FileNotFoundError:
        return {} 

def speichere_teams(daten):
    with open("teams.json", "w") as datei:
        json.dump(daten, datei, ensure_ascii=False, indent=4)


#Hilfsfunktion für Rollen--------------------------------------------------
#gibt die echten Discord-Mitglieder zurück, oder None wenn einer fehlt
async def real_discord(spieler, guild, interaction: discord.Interaction):
    mitglieder = []
    for name in spieler:
        mitglied = guild.get_member_named(name)
        if mitglied is None:
            await interaction.followup.send(f"`{name}` wurde auf dem Server nicht gefunden!", ephemeral=True)
            return None
        mitglieder.append(mitglied)
    return mitglieder

#für die Teamanmeldung-------------------------------------------------------
class Anmeldung(discord.ui.Modal, title="Anmeldung - max 4.Spieler"):
    #Echte Discord namen verwenden!!!!
    teamname = discord.ui.TextInput(
        label="Teamname",
        placeholder="z.B. Die Orangen",
        max_length=32,
    )
    Leader = discord.ui.TextInput(label="Leader", placeholder="Discord-Name", max_length=32)
    name2 = discord.ui.TextInput(label="Player2", placeholder="Discord-Name", max_length=32, required=False)
    name3 = discord.ui.TextInput(label="Player3", placeholder="Discord-Name", max_length=32, required=False)
    name4 = discord.ui.TextInput(label="Player4", placeholder="Discord-Name", max_length=32, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        # wird ausgeführt, wenn jemand auf "Absenden" klickt
        # defer = "ich arbeite dran", damit die 3-Sekunden-Grenze nicht greift.
        # Danach wird mit interaction.followup.send geantwortet.
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        teamname = self.teamname.value.strip()
        felder = [self.Leader, self.name2, self.name3, self.name4]
        spieler = []
        for feld in felder:
            name = feld.value.strip()
            if name != "":
                spieler.append(name)

        # Namen -> echte Discord-Mitglieder
        mitglieder = await real_discord(spieler, guild, interaction)
        if mitglieder is None:
            return

        daten = lade_teams()
        if teamname in daten:
            await interaction.followup.send("Der Teamname ist schon vergeben!!", ephemeral=True)
            return
        for teams in daten:
            for player in daten[teams]:
                if player in spieler:
                    await interaction.followup.send(f"`{player}` ist schon im Team **{teams}**!!", ephemeral=True)
                    return

        # Rollen erstellen und vergeben
        teamrolle = await guild.create_role(name=teamname)
        anführer_rolle = await guild.create_role(name="Anführer " + teamname)
        for mitglied in mitglieder:
            await mitglied.add_roles(teamrolle)
        await mitglieder[0].add_roles(anführer_rolle)
        # privaten Team-Channel erstellen
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),  # @everyone sieht ihn nicht
            teamrolle: discord.PermissionOverwrite(view_channel=True),            # das Team schon
            guild.me: discord.PermissionOverwrite(view_channel=True),             # der Bot auch
        }
        kategorie = guild.get_channel(TEAM_CATEGORY_ID) if TEAM_CATEGORY_ID else None
        kanal = await guild.create_text_channel(teamname, overwrites=overwrites, category=kategorie)
        await kanal.send(f"Willkommen, Team **{teamname}**! {teamrolle.mention}")
        # erst jetzt speichern (Namen, keine Member-Objekte)
        daten[teamname] = spieler
        speichere_teams(daten)

        await interaction.followup.send(f"Angemeldet: {teamname}", ephemeral=True)
        await postteam(teamname, spieler)


#Das Report Modal-----------------------------------------------------------
class Report(discord.ui.Modal, title="Regelverstoß melden (max. 2 pro Tag)"):
    betreff = discord.ui.TextInput(
        label="Betreff",
        max_length=32,
    )
    problem = discord.ui.TextInput(
        label="Problem",
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        heute = date.today()
        name = interaction.user.name
        datum, anzahl = ticket_zaehler.get(user_id, (heute, 0))
        if datum != heute:
            anzahl = 0
        if anzahl < 2:
            ticket_zaehler[user_id] = (heute, anzahl + 1)
            await send_report(self.betreff.value, self.problem.value, name, heute)
            await interaction.response.send_message("Danke, dein Report wurde gesendet!", ephemeral=True)
        else:
            await interaction.response.send_message("Du hast heute schon 2 Reports geschrieben.", ephemeral=True)


#Die Buttons für die Mods (Whitelist-Anfrage)-------------------------------
class WhitelistAnfrage(discord.ui.View):
    def __init__(self, mc_name, mitglied):
        super().__init__(timeout=None)  # Buttons laufen nie ab
        self.mc_name = mc_name
        self.mitglied = mitglied        # das discord.Member-Objekt
    
    #deaktiviert die interaktion
    def buttons_deaktivieren(self):
        # self.children = alle Buttons dieser View
        for item in self.children:
            item.disabled = True

    @discord.ui.button(label="Annehmen", style=discord.ButtonStyle.green)
    async def annehmen(self, interaction: discord.Interaction, button: discord.ui.Button):
        username = self.mitglied.name
        mc_name = self.mc_name
        daten = lade_spieler()

        # ist der spieler schon auf der whitelist?
        if username in daten:
            self.buttons_deaktivieren()
            await interaction.response.edit_message(
                content=f"ℹ️ {self.mitglied.mention} ist schon gewhitelisted (`{daten[username]}`).",
                view=self,
            )
            return

        # player wird gewhitelisted
        try:
            with MCRcon(RCON_HOST, os.environ["RCON_PASSWORD"], port=RCON_PORT) as rcon:
                antwort = rcon.command(f"whitelist add {mc_name}")
        except MCRconException:
            await interaction.response.send_message(
                "❌ RCON-Login fehlgeschlagen. Ist das Passwort in der `.env` richtig?"
            )
            return
        except ConnectionRefusedError:
            await interaction.response.send_message(
                "❌ Server nicht erreichbar. Läuft der Minecraft-Server und ist RCON aktiviert?"
            )
            return
        except TimeoutError:
            await interaction.response.send_message(
                "❌ Server antwortet nicht. Stimmt die IP bzw. blockiert die Firewall?"
            )
            return
        except Exception as e:
            print(f"Unbekannter RCON-Fehler: {e}")
            await interaction.response.send_message(f"❌ Unbekannter Fehler: `{e}`")
            return

        #schaut ob der server überhaupt annimmt
        if "Added" not in antwort and "already" not in antwort:
            await interaction.response.send_message(f"❌ Server sagt: `{antwort}`")
            return

        #speichert in json
        daten[username] = mc_name
        speichere_spieler(daten)

        # 4. Buttons deaktivieren und Nachricht im Mod-Channel bearbeiten
        self.buttons_deaktivieren()
        await interaction.response.edit_message(
            content=f"✅ {self.mitglied.mention} (`{mc_name}`) wurde von {interaction.user.mention} angenommen.",
            view=self,
        )

        # 5. Spieler-Channel informieren
        spieler_channel = bot.get_channel(PLAYER_CHANNEL_ID)
        if spieler_channel is not None:
            await spieler_channel.send(f"🎉 {self.mitglied.mention} wurde als `{mc_name}` gewhitelisted!")

    @discord.ui.button(label="Ablehnen", style=discord.ButtonStyle.red)
    async def ablehnen(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.buttons_deaktivieren()
        await interaction.response.edit_message(
            content=f"❌ Anfrage von {self.mitglied.mention} (`{self.mc_name}`) wurde von {interaction.user.mention} abgelehnt.",
            view=self,
        )
        # DM an den Spieler (klappt nicht, wenn er DMs deaktiviert hat)
        try:
            await self.mitglied.send("Deine Whitelist-Anfrage wurde leider abgelehnt.")
        except discord.Forbidden:
            pass


#Das Whitelist-Formular für die Spieler-------------------------------------
class WhitelistForm(discord.ui.Modal, title="Hier für die Whitelist anfragen"):
    mc_name = discord.ui.TextInput(label="Minecraft-Name", max_length=16)

    async def on_submit(self, interaction: discord.Interaction):
        username = interaction.user.name
        daten = lade_spieler()
        if username in daten:
            await interaction.response.send_message("Du bist schon registriert!", ephemeral=True)
            return

        channel = bot.get_channel(MOD_CHANNEL_ID)
        if channel is None:
            await interaction.response.send_message("Gerade nicht möglich, versuch's später nochmal.", ephemeral=True)
            return

        mc_name = self.mc_name.value.strip()
        await channel.send(
            f"Whitelist-Anfrage von {interaction.user.mention}: `{mc_name}`",
            view=WhitelistAnfrage(mc_name, interaction.user),
        )
        await interaction.response.send_message("Deine Anfrage wurde an die Mods geschickt!", ephemeral=True)


@bot.event
async def setup_hook():
    # Registriert die Slash-Commands bei Discord
    await bot.tree.sync()


@bot.event
async def on_ready():
    print(f"Eingeloggt als {bot.user}")


#Funktionen die keine Commands sind-----------------------------------------

#sendet das team mit teamnamen in den Teamchannel
async def postteam(teamname, spieler):
    channel = bot.get_channel(TEAM_CHANNEL_ID)
    if channel is None:
        print("Team-Channel nicht gefunden!")
        return
    text = ""
    for name in range(1, len(spieler)):
        text += "\n**Spieler " + str(name + 1) + "**: " + str(spieler[name])
    await channel.send(f"Team: **{teamname}**\n**Anführer**: {spieler[0]}{text}")


#sendet den report in den Modchannel
async def send_report(betreff, problem, name, heute):
    channel = bot.get_channel(MOD_CHANNEL_ID)
    if channel is None:
        print("Mod-Channel nicht gefunden!")
        return
    await channel.send(
        f"**{name}** hat mit folgendem Betreff: **{betreff}** am {heute.strftime('%d.%m.%Y')} folgendes Problem:\n{problem}"
    )


#Commands für den Bot-------------------------------------------------------
@bot.tree.command(name="hallo", description="Sagt hallo")
async def hallo(interaction: discord.Interaction):
    await interaction.response.send_message(f"Hey {interaction.user.mention}! 👋")


@bot.tree.command(name="parlaiment", description="was ist das parlament eigentlich?")
async def parlaiment(interaction: discord.Interaction):
    await interaction.response.send_message("Lückenfüller", ephemeral=True)


#Commands zur Server Ip-----------------------------------------------------
@bot.tree.command(name="setip", description="die Ip für den Server ändern")
@app_commands.default_permissions(administrator=True)
async def change_ip(interaction: discord.Interaction, ip: str):
    global Server_IP
    Server_IP = ip
    await interaction.response.send_message(f"Server-IP ist jetzt: `{Server_IP}`", ephemeral=True)


@bot.tree.command(name="ip", description="bekomme die server IP")
async def ip(interaction: discord.Interaction):
    await interaction.response.send_message(f"Die IP ist: `{Server_IP}`", ephemeral=True)


#Alle Forms Commands--------------------------------------------------------
@bot.tree.command(name="report", description="Was ist das Problem?")
async def report(interaction: discord.Interaction):
    await interaction.response.send_modal(Report())


@bot.tree.command(name="teamanmeldung", description="assigns teams together")
async def teamanmeldung(interaction: discord.Interaction):
    await interaction.response.send_modal(Anmeldung())


@bot.tree.command(name="apply_whitelist", description="Bewerbe dich für die Server-Whitelist")
async def apply_whitelist(interaction: discord.Interaction):
    if whitelist_flag:
        await interaction.response.send_modal(WhitelistForm())
    else:
        await interaction.response.send_message("Whitelist ist noch nicht aktiviert", ephemeral=True)


bot.run(os.environ["DISCORD_TOKEN"])
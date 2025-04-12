#===================================
# SILLYTAVERN DISCORD BOT
#===================================
# A Discord bot that connects SillyTavern characters to Discord channels
# Uses Selenium to control SillyTavern's web interface

import os
import discord
import asyncio
import time
import json
from discord.ext import commands
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

#===================================
# CONFIGURATION
#===================================

# Load config from config.json
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    # Default config
    config = {
        "SILLYTAVERN_URL": "http://localhost:8000",  # Default SillyTavern URL
        "CHARACTER_NAME": "Assistant",               # Default character name
        "DISCORD_CHANNEL_ID": None,                  # Discord channel ID to listen to
        "SELENIUM_DRIVER": "chrome",                 # chrome, edge, or firefox
        "DRIVER_PATH": None,                         # Path to your webdriver (if needed)
        "RESPONSE_TIMEOUT": 60,                      # How long to wait for AI response (seconds)
        "USE_PERSONAS": False                        # Whether to use SillyTavern personas
    }
    # Save default config
    with open('config.json', 'w') as f:
        json.dump(config, f, indent=4)
    print("Created default config.json file. Please edit it with your settings.")

# Discord bot token from environment variable
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    print("ERROR: No Discord token found. Please add your token to the .env file.")
    exit(1)

# Setup Discord intents (permissions)
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
bot = commands.Bot(command_prefix='!', intents=intents)

#===================================
# SELENIUM SETUP
#===================================

def setup_webdriver():
    """Initialize and configure the Selenium webdriver"""
    print(f"Setting up {config['SELENIUM_DRIVER']} webdriver...")
    
    if config['SELENIUM_DRIVER'].lower() == 'chrome':
        options = webdriver.ChromeOptions()
        # Add options for better performance
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        if config['DRIVER_PATH']:
            return webdriver.Chrome(executable_path=config['DRIVER_PATH'], options=options)
        else:
            return webdriver.Chrome(options=options)
            
    elif config['SELENIUM_DRIVER'].lower() == 'edge':
        options = webdriver.EdgeOptions()
        # Add options for better performance
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        if config['DRIVER_PATH']:
            return webdriver.Edge(executable_path=config['DRIVER_PATH'], options=options)
        else:
            return webdriver.Edge(options=options)
            
    elif config['SELENIUM_DRIVER'].lower() == 'firefox':
        options = webdriver.FirefoxOptions()
        # Add options for better performance
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        
        if config['DRIVER_PATH']:
            return webdriver.Firefox(executable_path=config['DRIVER_PATH'], options=options)
        else:
            return webdriver.Firefox(options=options)
    else:
        print(f"Unsupported driver: {config['SELENIUM_DRIVER']}. Using Chrome as default.")
        options = webdriver.ChromeOptions()
        return webdriver.Chrome(options=options)

#===================================
# SILLYTAVERN INTERACTION
#===================================

class SillyTavernController:
    def __init__(self):
        self.driver = None
        self.connected = False
        self.current_character = None
    
    async def connect(self):
        """Connect to SillyTavern and initialize the session"""
        try:
            self.driver = setup_webdriver()
            self.driver.get(config['SILLYTAVERN_URL'])
            
            # Wait for SillyTavern to load
            print("Waiting for SillyTavern to load...")
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".character_select"))
            )
            
            # Select the character
            await self.select_character(config['CHARACTER_NAME'])
            self.connected = True
            return True
            
        except Exception as e:
            print(f"Error connecting to SillyTavern: {e}")
            if self.driver:
                self.driver.quit()
            self.driver = None
            self.connected = False
            return False
    
    async def select_character(self, character_name):
        """Select a character in SillyTavern by name"""
        try:
            print(f"Selecting character: {character_name}")
            
            # Wait for character select to be available
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".character_select"))
            )
            
            # Click on character select to show the dropdown
            self.driver.find_element(By.CSS_SELECTOR, ".character_select").click()
            
            # Wait for character list to appear
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#character-selector-list"))
            )
            
            # Find and click on the character by name
            character_items = self.driver.find_elements(By.CSS_SELECTOR, ".character_select_item")
            
            for item in character_items:
                character_name_element = item.find_element(By.CSS_SELECTOR, ".ch_name")
                if character_name_element.text.strip() == character_name:
                    item.click()
                    self.current_character = character_name
                    print(f"Selected character: {character_name}")
                    # Allow time for character to load
                    await asyncio.sleep(2)
                    return True
            
            print(f"Character '{character_name}' not found in the list.")
            return False
            
        except Exception as e:
            print(f"Error selecting character: {e}")
            return False
    
    async def send_message(self, message, user_id=None, username=None):
        """Send a message to SillyTavern and get the response"""
        try:
            if not self.connected or not self.driver:
                print("Not connected to SillyTavern. Reconnecting...")
                if not await self.connect():
                    return "Error: Could not connect to SillyTavern."
            
            # If using personas and username is provided, set the persona
            if config['USE_PERSONAS'] and username:
                await self.set_persona(username, user_id)
            
            # Find the message input field
            input_field = self.driver.find_element(By.ID, "send_textarea")
            
            # Clear the input field and enter the message
            input_field.clear()
            input_field.send_keys(message)
            
            # Send the message
            input_field.send_keys(Keys.RETURN)
            
            # Wait for AI to respond
            return await self.wait_for_response()
            
        except Exception as e:
            print(f"Error sending message: {e}")
            return f"Error sending message: {str(e)}"
    
    async def wait_for_response(self):
        """Wait for and extract the AI's response"""
        try:
            # Initial message count
            initial_messages = self.driver.find_elements(By.CSS_SELECTOR, ".mes_text")
            initial_count = len(initial_messages)
            
            # Wait for the "thinking" indicator to appear and then disappear
            try:
                # First wait for thinking indicator to appear (optional)
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".typing_indicator"))
                )
                
                # Then wait for it to disappear (meaning the response is complete)
                WebDriverWait(self.driver, config['RESPONSE_TIMEOUT']).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".typing_indicator"))
                )
            except TimeoutException:
                # If we didn't see the typing indicator, that's fine
                pass
            
            # Give a short delay to ensure message is rendered
            await asyncio.sleep(1)
            
            # Get all messages now
            messages = self.driver.find_elements(By.CSS_SELECTOR, ".mes_text")
            
            # If we have new messages
            if len(messages) > initial_count:
                # Get the latest message (the AI's response)
                latest_message = messages[-1].text.strip()
                return latest_message
            else:
                # Try an alternative method - get the last message with the character's name
                char_messages = self.driver.find_elements(By.CSS_SELECTOR, f".mes[ch_name='{self.current_character}']")
                if char_messages:
                    latest_char_message = char_messages[-1].find_element(By.CSS_SELECTOR, ".mes_text").text.strip()
                    return latest_char_message
                
                return "No response was detected from the AI."
                
        except Exception as e:
            print(f"Error waiting for response: {e}")
            return f"Error getting AI response: {str(e)}"
    
    async def set_persona(self, username, user_id=None):
        """Set the persona for the current user"""
        try:
            # Default to "Unknown Person" if the username isn't recognized
            persona_name = "Unknown Person"
            
            # Map Discord user IDs to persona names
            # This could be expanded to load from a JSON file
            persona_mapping = {
                # Example: "123456789012345678": "John Doe",
            }
            
            # If we have a mapping for this user ID, use it
            if user_id and user_id in persona_mapping:
                persona_name = persona_mapping[user_id]
            
            # Type the /persona command in the input field
            input_field = self.driver.find_element(By.ID, "send_textarea")
            input_field.clear()
            input_field.send_keys(f"/persona {persona_name}")
            input_field.send_keys(Keys.RETURN)
            
            # Wait a moment for the persona to be applied
            await asyncio.sleep(1)
            
            print(f"Set persona to {persona_name} for user {username}")
            return True
            
        except Exception as e:
            print(f"Error setting persona: {e}")
            return False
    
    def disconnect(self):
        """Close the browser and clean up"""
        if self.driver:
            self.driver.quit()
            self.driver = None
        self.connected = False
        print("Disconnected from SillyTavern")

# Initialize the SillyTavern controller
st_controller = SillyTavernController()

#===================================
# DISCORD BOT EVENTS
#===================================

@bot.event
async def on_ready():
    """Called when the bot is ready and connected to Discord"""
    print(f'{bot.user.name} has connected to Discord!')
    
    # Connect to SillyTavern
    if await st_controller.connect():
        print("Successfully connected to SillyTavern!")
    else:
        print("Failed to connect to SillyTavern. Please check your configuration.")

@bot.event
async def on_message(message):
    """Called when a message is received in Discord"""
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return
    
    # Only process messages in the configured channel
    if config['DISCORD_CHANNEL_ID'] and message.channel.id != int(config['DISCORD_CHANNEL_ID']):
        return
    
    # Process commands (like !help)
    await bot.process_commands(message)
    
    # Handle regular messages
    if not message.content.startswith(bot.command_prefix):
        # Send typing indicator to show the bot is processing
        async with message.channel.typing():
            # Forward the message to SillyTavern
            response = await st_controller.send_message(
                message.content,
                user_id=str(message.author.id),
                username=message.author.name
            )
            
            # Send the response back to Discord
            await message.channel.send(response)

#===================================
# BOT COMMANDS
#===================================

@bot.command(name='reconnect')
async def reconnect_command(ctx):
    """Reconnect to SillyTavern"""
    await ctx.send("Reconnecting to SillyTavern...")
    
    # Disconnect if already connected
    st_controller.disconnect()
    
    # Attempt to connect
    if await st_controller.connect():
        await ctx.send("Successfully reconnected to SillyTavern!")
    else:
        await ctx.send("Failed to reconnect to SillyTavern. Please check your configuration.")

@bot.command(name='character')
async def change_character(ctx, *, character_name):
    """Change the active character"""
    await ctx.send(f"Changing character to {character_name}...")
    
    # Attempt to select the new character
    if await st_controller.select_character(character_name):
        # Update the config
        config['CHARACTER_NAME'] = character_name
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=4)
        
        await ctx.send(f"Successfully changed to character: {character_name}")
    else:
        await ctx.send(f"Failed to find character: {character_name}")

@bot.command(name='help')
async def help_command(ctx):
    """Show help information"""
    help_text = """
**SillyTavern Discord Bot Commands**

`!reconnect` - Reconnect to SillyTavern
`!character <name>` - Change to a different character
`!help` - Show this help message

Regular messages sent in this channel will be forwarded to SillyTavern.
"""
    await ctx.send(help_text)

#===================================
# MAIN FUNCTION
#===================================

def main():
    """Main function to start the bot"""
    try:
        print("Starting SillyTavern Discord Bot...")
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        print("Shutting down...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Ensure we disconnect from SillyTavern
        st_controller.disconnect()

if __name__ == "__main__":
    main()

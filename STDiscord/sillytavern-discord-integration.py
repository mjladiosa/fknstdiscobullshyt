# ===================================
# SILLYTAVERN DISCORD BOT (Improved)
# ===================================
# A Discord bot that connects SillyTavern characters to Discord channels
# Uses Selenium to control SillyTavern's web interface

import os
import discord
import asyncio
import time
import json
import logging
from typing import Optional, Dict, List, Any
from discord.ext import commands
from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ===================================
# LOGGING SETUP
# ===================================
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# ===================================
# CONFIGURATION
# ===================================

DEFAULT_CONFIG_PATH = 'config.json'

def load_configuration() -> Dict[str, Any]:
    """Loads configuration from JSON file or creates a default one."""
    try:
        with open(DEFAULT_CONFIG_PATH, 'r') as f:
            logging.info(f"Loading configuration from {DEFAULT_CONFIG_PATH}")
            return json.load(f)
    except FileNotFoundError:
        logging.warning(f"{DEFAULT_CONFIG_PATH} not found. Creating default configuration.")
        default_config = {
            "SILLYTAVERN_URL": "http://localhost:8000",
            "DEFAULT_CHARACTER_NAME": "Assistant",
            "DISCORD_CHANNEL_ID": None,
            "SELENIUM_DRIVER": "chrome",  # Options: "chrome", "edge", "firefox"
            "DRIVER_PATH": None,         # Optional: Path to your webdriver executable
            "RESPONSE_TIMEOUT": 60,      # Seconds to wait for AI response
            "USE_PERSONAS": False,
            "PERSONA_MAPPING": {         # Map Discord User IDs (str) to SillyTavern persona names (str)
                # "123456789012345678": "PersonaForUser1",
                # "987654321098765432": "PersonaForUser2"
            },
            "HEADLESS_BROWSER": False    # Run browser in headless mode (no GUI)
        }
        try:
            with open(DEFAULT_CONFIG_PATH, 'w') as f:
                json.dump(default_config, f, indent=4)
            logging.info(f"Created default {DEFAULT_CONFIG_PATH}. Please edit it with your settings.")
            return default_config
        except IOError as e:
            logging.error(f"Could not write default config file: {e}")
            exit(1)
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding {DEFAULT_CONFIG_PATH}: {e}")
        exit(1)

config = load_configuration()

# Discord bot token from environment variable
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not DISCORD_TOKEN:
    logging.error("ERROR: No Discord token found. Please add your token to the .env file.")
    exit(1)

# Setup Discord intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ===================================
# SELENIUM SETUP & CONSTANTS
# ===================================

# CSS Selectors (makes updates easier)
CHARACTER_SELECT_DROPDOWN = ".character_select" # Or find a more specific selector if needed
CHARACTER_LIST_CONTAINER = "#character-selector-list" # Or the actual ID/class
CHARACTER_LIST_ITEM = ".character_select_item" # Or the actual class
CHARACTER_NAME_IN_ITEM = ".ch_name" # Or the actual class
MESSAGE_INPUT_TEXTAREA = "#send_textarea"
MESSAGE_CONTAINER = ".mes" # General message container
MESSAGE_TEXT = ".mes_text" # Text within a message
TYPING_INDICATOR = ".typing_indicator" # Class for the '...' indicator

def setup_webdriver() -> Optional[WebDriver]:
    """Initialize and configure the Selenium webdriver based on config."""
    driver_type = config.get('SELENIUM_DRIVER', 'chrome').lower()
    driver_path = config.get('DRIVER_PATH')
    headless = config.get('HEADLESS_BROWSER', False)
    logging.info(f"Setting up {driver_type} webdriver... Headless: {headless}")

    options: Optional[webdriver.ChromeOptions | webdriver.EdgeOptions | webdriver.FirefoxOptions] = None

    try:
        if driver_type == 'chrome':
            options = webdriver.ChromeOptions()
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            if headless:
                options.add_argument('--headless')
                options.add_argument("--window-size=1920,1080") # Needed for headless
            if driver_path:
                service = webdriver.ChromeService(executable_path=driver_path)
                return webdriver.Chrome(service=service, options=options)
            else:
                # Consider adding webdriver-manager for automatic driver download
                # from webdriver_manager.chrome import ChromeDriverManager
                # service = webdriver.ChromeService(ChromeDriverManager().install())
                # return webdriver.Chrome(service=service, options=options)
                return webdriver.Chrome(options=options) # Assumes chromedriver is in PATH

        elif driver_type == 'edge':
            options = webdriver.EdgeOptions()
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            if headless:
                options.add_argument('--headless')
                options.add_argument("--window-size=1920,1080")
            if driver_path:
                service = webdriver.EdgeService(executable_path=driver_path)
                return webdriver.Edge(service=service, options=options)
            else:
                # Consider webdriver-manager
                return webdriver.Edge(options=options) # Assumes msedgedriver is in PATH

        elif driver_type == 'firefox':
            options = webdriver.FirefoxOptions()
            options.add_argument('--disable-gpu')
            # Firefox sandbox is generally more stable
            # options.add_argument('--no-sandbox') # Less common for Firefox
            if headless:
                options.add_argument('--headless')
                options.add_argument("--window-size=1920,1080")
            if driver_path:
                service = webdriver.FirefoxService(executable_path=driver_path)
                return webdriver.Firefox(service=service, options=options)
            else:
                # Consider webdriver-manager
                return webdriver.Firefox(options=options) # Assumes geckodriver is in PATH
        else:
            logging.error(f"Unsupported driver type: {driver_type}. Please choose 'chrome', 'edge', or 'firefox'.")
            return None

    except WebDriverException as e:
        logging.error(f"WebDriver setup failed: {e}")
        logging.error("Ensure the correct webdriver executable is installed and accessible (either in PATH or via DRIVER_PATH config).")
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred during webdriver setup: {e}")
        return None

# ===================================
# SILLYTAVERN INTERACTION
# ===================================

class SillyTavernController:
    def __init__(self):
        self.driver: Optional[WebDriver] = None
        self.connected: bool = False
        self.current_character: Optional[str] = None
        self.last_message_id: Optional[str] = None # To help track new messages

    async def connect(self) -> bool:
        """Connect to SillyTavern, initialize the session, and select the character."""
        if self.connected and self.driver:
            logging.info("Already connected.")
            return True

        self.driver = setup_webdriver()
        if not self.driver:
            self.connected = False
            return False

        try:
            logging.info(f"Navigating to SillyTavern URL: {config['SILLYTAVERN_URL']}")
            self.driver.get(config['SILLYTAVERN_URL'])

            # Wait for a key element indicating SillyTavern has loaded (e.g., character select or chat input)
            logging.info("Waiting for SillyTavern interface to load...")
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, MESSAGE_INPUT_TEXTAREA))
            )
            logging.info("SillyTavern interface loaded.")

            # Select the initial character
            initial_char = config.get('DEFAULT_CHARACTER_NAME', 'Assistant')
            if await self.select_character(initial_char):
                self.connected = True
                logging.info(f"Successfully connected and selected character: {self.current_character}")
                # Get the ID of the last message currently visible
                self._update_last_message_id()
                return True
            else:
                logging.error(f"Failed to select initial character: {initial_char}")
                await self.disconnect() # Clean up if character selection fails
                return False

        except TimeoutException:
            logging.error(f"Timeout waiting for SillyTavern to load at {config['SILLYTAVERN_URL']}.")
            await self.disconnect()
            return False
        except WebDriverException as e:
            logging.error(f"WebDriver error during connection: {e}")
            await self.disconnect()
            return False
        except Exception as e:
            logging.error(f"Unexpected error connecting to SillyTavern: {e}")
            await self.disconnect()
            return False

    async def select_character(self, character_name: str) -> bool:
        """Selects a character in SillyTavern by name."""
        if not self.driver:
            logging.error("Cannot select character: WebDriver not initialized.")
            return False

        try:
            logging.info(f"Attempting to select character: {character_name}")

            # Wait for the character select dropdown to be clickable
            char_select_element = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, CHARACTER_SELECT_DROPDOWN))
            )
            char_select_element.click()

            # Wait for the character list container to be visible
            WebDriverWait(self.driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, CHARACTER_LIST_CONTAINER))
            )

            # Find the specific character list item
            # Use XPath for contains text - more robust if exact match fails
            xpath_selector = f"//{CHARACTER_LIST_ITEM.strip('.')}//{CHARACTER_NAME_IN_ITEM.strip('.')} [normalize-space()='{character_name}']//ancestor::{CHARACTER_LIST_ITEM.strip('.')}"

            try:
                character_item = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, xpath_selector))
                )
                character_item.click()
                self.current_character = character_name
                logging.info(f"Successfully selected character: {character_name}")
                # Allow brief moment for UI update after selection
                await asyncio.sleep(2)
                self._update_last_message_id() # Update message marker after potentially loading new chat
                return True

            except TimeoutException:
                logging.warning(f"Character '{character_name}' not found using exact match or XPath.")
                # Fallback: Iterate through visible names if XPath fails (less efficient)
                try:
                    char_items = self.driver.find_elements(By.CSS_SELECTOR, CHARACTER_LIST_ITEM)
                    for item in char_items:
                        name_element = item.find_element(By.CSS_SELECTOR, CHARACTER_NAME_IN_ITEM)
                        if name_element.text.strip() == character_name:
                            logging.info("Found character via fallback iteration.")
                            item.click()
                            self.current_character = character_name
                            await asyncio.sleep(2)
                            self._update_last_message_id()
                            return True
                    logging.error(f"Character '{character_name}' not found in the list (fallback failed).")
                    # Maybe click elsewhere to close dropdown?
                    try: self.driver.find_element(By.TAG_NAME, 'body').click()
                    except: pass
                    return False
                except NoSuchElementException:
                    logging.error("Could not find character list items for fallback.")
                    return False

        except TimeoutException as e:
            logging.error(f"Timeout occurred during character selection: {e}")
            return False
        except NoSuchElementException as e:
            logging.error(f"Could not find required elements for character selection: {e}")
            return False
        except Exception as e:
            logging.error(f"Error selecting character '{character_name}': {e}")
            return False

    def _get_all_messages(self) -> List[WebElement]:
        """Safely gets all message elements."""
        if not self.driver: return []
        try:
            return self.driver.find_elements(By.CSS_SELECTOR, MESSAGE_CONTAINER)
        except NoSuchElementException:
            return []

    def _update_last_message_id(self):
        """Stores the ID (or unique attribute) of the last message element."""
        if not self.driver: return
        messages = self._get_all_messages()
        if messages:
            try:
                # Using a potentially unique attribute like 'mesid' if available, or just rely on index
                self.last_message_id = messages[-1].get_attribute('id') or messages[-1].get_attribute('mesid') or str(len(messages) -1)
            except Exception as e:
                logging.warning(f"Could not get ID for last message: {e}")
                self.last_message_id = str(len(messages) - 1) # Fallback to index
        else:
            self.last_message_id = None
        logging.debug(f"Last message marker updated: {self.last_message_id}")


    async def send_message(self, message: str, user_id: Optional[str] = None, username: Optional[str] = None) -> str:
        """Sends a message to SillyTavern and retrieves the character's response."""
        if not self.connected or not self.driver:
            logging.warning("Not connected to SillyTavern. Attempting to reconnect...")
            if not await self.connect():
                return "Error: Could not connect to SillyTavern."

        try:
            # 1. Set Persona (if applicable)
            if config.get('USE_PERSONAS', False) and username:
                await self.set_persona(username, user_id)

            # 2. Find input field
            input_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, MESSAGE_INPUT_TEXTAREA))
            )

            # 3. Store state before sending
            self._update_last_message_id() # Get the latest message ID before sending new one

            # 4. Send the message
            logging.info(f"Sending message to ST: '{message[:50]}...'")
            input_field.clear()
            input_field.send_keys(message)
            input_field.send_keys(Keys.RETURN)

            # 5. Wait for and extract the response
            return await self._wait_for_response()

        except TimeoutException:
            logging.error("Timeout finding message input field.")
            return "Error: Could not find the message input area in SillyTavern."
        except NoSuchElementException:
            logging.error("Message input field not found.")
            return "Error: Could not find the message input area in SillyTavern."
        except WebDriverException as e:
            logging.error(f"WebDriver error during message sending: {e}")
            self.connected = False # Assume connection is broken
            return f"Error interacting with SillyTavern: {str(e)}"
        except Exception as e:
            logging.error(f"Unexpected error sending message: {e}")
            return f"An unexpected error occurred: {str(e)}"

    async def _wait_for_response(self) -> str:
        """Waits for the character's response after a message is sent."""
        if not self.driver or not self.current_character:
            return "Error: Not connected or no character selected."

        timeout = config.get('RESPONSE_TIMEOUT', 60)
        start_time = time.time()
        logging.info(f"Waiting for response from {self.current_character} (timeout: {timeout}s)")

        try:
            # Wait condition: EITHER typing indicator disappears OR a new message from the character appears
            wait = WebDriverWait(self.driver, timeout)

            # Define a custom expected condition
            def condition_met(driver: WebDriver) -> Optional[WebElement]:
                # Check if typing indicator exists and is visible
                try:
                    indicator = driver.find_element(By.CSS_SELECTOR, TYPING_INDICATOR)
                    if indicator.is_displayed():
                        # Still typing, continue waiting (return False)
                        return None # Indicate still waiting
                except NoSuchElementException:
                    # Typing indicator not found/gone, proceed to check for new message
                    pass

                # Check for new messages from the specific character after the last known message
                all_messages = self._get_all_messages()
                last_message_index = -1

                # Find the index of the last message we knew about
                if self.last_message_id:
                    found = False
                    for i, msg in enumerate(reversed(all_messages)):
                        try:
                            msg_id = msg.get_attribute('id') or msg.get_attribute('mesid') or str(len(all_messages) - 1 - i)
                            if msg_id == self.last_message_id:
                                last_message_index = len(all_messages) - 1 - i
                                found = True
                                break
                        except: continue # Ignore stale elements if chat refreshed
                    if not found:
                       logging.warning("Last known message ID not found, checking from start.")
                       last_message_index = -1 # Re-check from the beginning


                # Look for messages *after* the last_message_index
                for i in range(last_message_index + 1, len(all_messages)):
                    msg = all_messages[i]
                    try:
                        # Check if this message is from the expected character
                        # Assuming character name is stored in an attribute like 'ch' or 'ch_name'
                        msg_char_name = msg.get_attribute('ch') or msg.get_attribute('ch_name')
                        if msg_char_name and msg_char_name.strip() == self.current_character:
                            # Found a new message from the character
                            return msg # Return the WebElement
                    except Exception as e:
                         # Handle potential stale element reference if DOM changes rapidly
                        logging.debug(f"Stale element encountered while checking messages: {e}")
                        return None # Re-evaluate on next check

                # If typing indicator is gone AND no new message found yet, keep waiting briefly
                # Or if timeout is approaching, maybe return early? For now, just return None.
                return None # Indicate still waiting


            # Execute the wait with the custom condition
            new_message_element = wait.until(condition_met)

            if new_message_element:
                response_text = new_message_element.find_element(By.CSS_SELECTOR, MESSAGE_TEXT).text.strip()
                logging.info(f"Received response: '{response_text[:50]}...'")
                self._update_last_message_id() # Update marker to this new message
                return response_text
            else:
                 # This case should ideally be covered by the timeout, but check just in case condition returns None incorrectly
                 logging.warning("Wait finished without finding a new message element, despite condition supposedly being met.")
                 # Fallback: Check last message again
                 all_messages = self._get_all_messages()
                 if all_messages:
                     last_msg = all_messages[-1]
                     msg_char_name = last_msg.get_attribute('ch') or last_msg.get_attribute('ch_name')
                     if msg_char_name and msg_char_name.strip() == self.current_character:
                         response_text = last_msg.find_element(By.CSS_SELECTOR, MESSAGE_TEXT).text.strip()
                         logging.info(f"Received response (fallback check): '{response_text[:50]}...'")
                         self._update_last_message_id()
                         return response_text

                 logging.warning("No response detected after wait.")
                 return "AI response not detected or timed out."


        except TimeoutException:
            logging.warning(f"Timeout waiting for response from {self.current_character}.")
            # Check if maybe the last message *is* the response, even if indicator didn't clear properly
            all_messages = self._get_all_messages()
            if all_messages:
                last_msg = all_messages[-1]
                try:
                    msg_char_name = last_msg.get_attribute('ch') or last_msg.get_attribute('ch_name')
                    if msg_char_name and msg_char_name.strip() == self.current_character:
                       msg_id = last_msg.get_attribute('id') or last_msg.get_attribute('mesid') or str(len(all_messages) -1)
                       # Check if this message is actually NEWER than our last known one
                       if msg_id != self.last_message_id: # Simple check, might need better logic if IDs aren't stable
                            response_text = last_msg.find_element(By.CSS_SELECTOR, MESSAGE_TEXT).text.strip()
                            logging.info(f"Received response (found after timeout): '{response_text[:50]}...'")
                            self._update_last_message_id()
                            return response_text
                except Exception as e:
                    logging.warning(f"Error during post-timeout check: {e}")

            return "AI response timed out."
        except NoSuchElementException as e:
             logging.error(f"Error finding message text within response element: {e}")
             return "Error extracting AI response text."
        except Exception as e:
            logging.error(f"Error waiting for/processing response: {e}")
            return f"Error getting AI response: {str(e)}"

    async def set_persona(self, username: str, user_id: Optional[str] = None) -> bool:
        """Sets the persona in SillyTavern using the /persona command."""
        if not self.driver: return False

        persona_map = config.get('PERSONA_MAPPING', {})
        # Default persona name if user not found in map
        default_persona = "User" # Or choose another default like "Discord User"
        persona_name = default_persona

        if user_id and user_id in persona_map:
            persona_name = persona_map[user_id]
            logging.info(f"Found persona '{persona_name}' for user ID {user_id} ({username})")
        else:
            logging.info(f"Using default persona '{persona_name}' for user {username} (ID: {user_id})")


        try:
            input_field = self.driver.find_element(By.CSS_SELECTOR, MESSAGE_INPUT_TEXTAREA)
            # Important: Use a space after /persona for the name
            command = f"/persona {persona_name}"
            logging.info(f"Setting persona using command: '{command}'")
            input_field.clear() # Clear first to avoid appending
            input_field.send_keys(command)
            input_field.send_keys(Keys.RETURN)

            # Short pause for command processing
            await asyncio.sleep(0.5)
            # We might need to clear the input again if ST leaves the command there
            try:
                current_input_value = input_field.get_attribute('value')
                if current_input_value == command:
                    input_field.clear()
            except: pass # Ignore if element stale

            return True

        except (NoSuchElementException, TimeoutException) as e:
            logging.error(f"Could not find input field to set persona: {e}")
            return False
        except Exception as e:
            logging.error(f"Error setting persona to '{persona_name}': {e}")
            return False

    async def disconnect(self):
        """Closes the browser and cleans up."""
        if self.driver:
            try:
                logging.info("Disconnecting from SillyTavern...")
                self.driver.quit()
            except Exception as e:
                logging.error(f"Error during webdriver quit: {e}")
            finally:
                self.driver = None
                self.connected = False
                self.current_character = None
                self.last_message_id = None
                logging.info("SillyTavern controller disconnected.")
        else:
            logging.info("SillyTavern controller already disconnected.")

# Initialize the SillyTavern controller
st_controller = SillyTavernController()

# ===================================
# DISCORD BOT EVENTS
# ===================================

@bot.event
async def on_ready():
    """Called when the bot is ready and connected to Discord."""
    logging.info(f'Discord bot logged in as {bot.user.name} ({bot.user.id})')
    logging.info('Attempting initial connection to SillyTavern...')
    if await st_controller.connect():
        logging.info("Bot is ready and connected to SillyTavern.")
        # Set status (optional)
        activity = discord.Activity(name=f"with {st_controller.current_character}", type=discord.ActivityType.playing)
        await bot.change_presence(activity=activity)
    else:
        logging.error("Bot is ready but FAILED to connect to SillyTavern. Check Selenium/ST setup.")
        # Maybe set status to indicate error?
        await bot.change_presence(status=discord.Status.dnd, activity=discord.Game(name="Connection Error"))


@bot.event
async def on_message(message: discord.Message):
    """Called when a message is received in Discord."""
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Check if message is in the designated channel (if configured)
    channel_id_str = config.get("DISCORD_CHANNEL_ID")
    if channel_id_str:
        try:
            target_channel_id = int(channel_id_str)
            if message.channel.id != target_channel_id:
                return # Ignore messages in other channels
        except ValueError:
            logging.warning(f"Invalid DISCORD_CHANNEL_ID in config: '{channel_id_str}'. Listening in all channels.")
            # Or exit(1) if channel lock is critical

    # Process bot commands first
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    # If not a command, and in the right channel, forward to SillyTavern
    logging.info(f"Received message from Discord user {message.author.name}: '{message.content[:50]}...'")

    # Show typing indicator in Discord while processing
    async with message.channel.typing():
        st_response = await st_controller.send_message(
            message.content,
            user_id=str(message.author.id), # Pass user ID for persona mapping
            username=message.author.name
        )

        # Send SillyTavern's response back to the Discord channel
        if st_response:
            # Split long messages if necessary (Discord limit is 2000 chars)
            for chunk in [st_response[i:i+1990] for i in range(0, len(st_response), 1990)]:
                 # Add slight delay between chunks if splitting
                 if len(st_response) > 1990 and chunk != st_response[0:1990]:
                     await asyncio.sleep(0.5)
                 await message.channel.send(chunk)
        else:
            # Handle cases where st_response might be empty or None unexpectedly
             logging.warning("Received empty response string from SillyTavern controller.")
             await message.channel.send("*Received an empty response from SillyTavern.*")

# ===================================
# BOT COMMANDS
# ===================================

@bot.command(name='st_reconnect', help='Disconnects and reconnects the bot to SillyTavern.')
@commands.is_owner() # Optional: Restrict command to bot owner
async def reconnect_command(ctx: commands.Context):
    """Reconnects the Selenium controller to SillyTavern."""
    await ctx.send("Attempting to reconnect to SillyTavern...")
    logging.info(f"Reconnect command initiated by {ctx.author.name}")
    await st_controller.disconnect()
    await asyncio.sleep(1) # Brief pause before reconnecting
    if await st_controller.connect():
        await ctx.send(f"✅ Successfully reconnected to SillyTavern with character: `{st_controller.current_character}`")
        activity = discord.Activity(name=f"with {st_controller.current_character}", type=discord.ActivityType.playing)
        await bot.change_presence(activity=activity)
    else:
        await ctx.send("❌ Failed to reconnect to SillyTavern. Check logs and configuration.")
        await bot.change_presence(status=discord.Status.dnd, activity=discord.Game(name="Connection Error"))


@bot.command(name='st_character', help='Changes the active SillyTavern character.')
@commands.is_owner() # Optional: Restrict command
async def change_character_command(ctx: commands.Context, *, character_name: str):
    """Changes the active SillyTavern character."""
    if not st_controller.connected or not st_controller.driver:
        await ctx.send("Not connected to SillyTavern. Please `!st_reconnect` first.")
        return

    await ctx.send(f"Attempting to change character to `{character_name}`...")
    logging.info(f"Character change command initiated by {ctx.author.name} for '{character_name}'")

    # Attempt to select the new character via Selenium
    if await st_controller.select_character(character_name):
        # Update the default character in the running config (doesn't save to file automatically)
        config['DEFAULT_CHARACTER_NAME'] = character_name
        # Optional: Save to config.json immediately?
        # try:
        #     with open(DEFAULT_CONFIG_PATH, 'w') as f:
        #         json.dump(config, f, indent=4)
        #     logging.info(f"Updated DEFAULT_CHARACTER_NAME in {DEFAULT_CONFIG_PATH}")
        # except IOError as e:
        #     logging.error(f"Could not save updated config: {e}")
        #     await ctx.send("⚠️ Changed character, but failed to save update to `config.json`.")

        await ctx.send(f"✅ Successfully changed character to: `{st_controller.current_character}`")
        activity = discord.Activity(name=f"with {st_controller.current_character}", type=discord.ActivityType.playing)
        await bot.change_presence(activity=activity)
    else:
        await ctx.send(f"❌ Failed to find or select character: `{character_name}`. Please check the name and SillyTavern.")
        # Revert config change if selection failed
        config['DEFAULT_CHARACTER_NAME'] = st_controller.current_character # Revert to the one that's actually selected


@bot.command(name='st_status', help='Checks the status of the SillyTavern connection.')
async def status_command(ctx: commands.Context):
    """Reports the current connection status and character."""
    if st_controller.connected and st_controller.current_character:
        status_msg = f"✅ Connected to SillyTavern.\nCurrent Character: `{st_controller.current_character}`"
        if config.get('USE_PERSONAS'):
            status_msg += f"\nPersona Mode: Enabled"
        else:
            status_msg += f"\nPersona Mode: Disabled"
    else:
        status_msg = "❌ Not connected to SillyTavern."
    await ctx.send(status_msg)

@bot.command(name='st_help', help='Shows help information for SillyTavern bot commands.')
async def help_command(ctx: commands.Context):
    """Shows help information specific to this bot."""
    help_embed = discord.Embed(title="SillyTavern Discord Bot Help", color=discord.Color.blue())
    help_embed.description = "Interact with a SillyTavern character through Discord."
    help_embed.add_field(name="💬 Usage", value="Simply type messages in the designated channel. The bot will forward them to SillyTavern and post the character's reply.", inline=False)
    help_embed.add_field(name="🤖 Commands", value=(
        f"`{bot.command_prefix}st_status` - Check connection status & current character.\n"
        f"`{bot.command_prefix}st_character <Character Name>` - Change the active ST character (owner only).\n"
        f"`{bot.command_prefix}st_reconnect` - Re-establish connection to ST (owner only).\n"
        f"`{bot.command_prefix}st_help` - Show this help message."
    ), inline=False)
    help_embed.set_footer(text=f"Using character: {st_controller.current_character if st_controller.connected else 'N/A'}")
    await ctx.send(embed=help_embed)

# ===================================
# MAIN FUNCTION & SHUTDOWN HANDLING
# ===================================

async def main():
    """Main async function to start the bot."""
    async with bot:
        logging.info("Starting SillyTavern Discord Bot...")
        try:
            await bot.start(DISCORD_TOKEN)
        except KeyboardInterrupt:
            logging.info("KeyboardInterrupt received. Shutting down...")
        except discord.LoginFailure:
            logging.error("Discord login failed. Check your DISCORD_TOKEN.")
        except Exception as e:
            logging.error(f"An error occurred running the bot: {e}")
        finally:
            logging.info("Disconnecting from SillyTavern before exiting...")
            await st_controller.disconnect()
            logging.info("Bot shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.critical(f"Critical error in main execution loop: {e}")
    finally:
        # Ensure Selenium driver is closed even if asyncio loop fails early
        if st_controller and st_controller.driver:
             logging.warning("Forcing SillyTavern disconnect outside of async loop.")
             # Cannot call async disconnect here, directly quit driver
             try:
                 st_controller.driver.quit()
             except Exception as eq:
                 logging.error(f"Error during final driver quit: {eq}")
                       

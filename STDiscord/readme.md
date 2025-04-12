# SillyTavern Discord Bot

A Discord bot that connects SillyTavern AI characters to Discord channels. This bot uses Selenium to automate interactions with the SillyTavern web interface, allowing your Discord server members to chat with SillyTavern characters.

## Features

- Forward messages from Discord to SillyTavern
- Send SillyTavern AI responses back to Discord
- Support for multiple characters (switch with commands)
- Optional persona support for different Discord users
- Simple setup with configuration files

## Prerequisites

- Python 3.8 or higher
- SillyTavern already installed and running
- A Discord bot token (from Discord Developer Portal)
- Chrome, Edge, or Firefox browser installed

## Installation

1. **Clone this repository**

```bash
git clone https://github.com/yourusername/sillytavern-discord-bot.git
cd sillytavern-discord-bot
```

2. **Install required Python packages**

```bash
pip install discord.py selenium python-dotenv
```

3. **Install WebDriver**

Depending on your browser choice:

- Chrome: [ChromeDriver](https://sites.google.com/chromium.org/driver/)
- Edge: [EdgeDriver](https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/)
- Firefox: [GeckoDriver](https://github.com/mozilla/geckodriver/releases)

Download the appropriate driver for your browser and operating system. Place it in a directory that's in your PATH, or specify the path in the config.json file.

4. **Configure the bot**

Edit the `.env` file:
```
DISCORD_TOKEN=your_discord_bot_token_here
```

Edit the `config.json` file:
```json
{
    "SILLYTAVERN_URL": "http://localhost:8000",
    "CHARACTER_NAME": "Your Character Name",
    "DISCORD_CHANNEL_ID": "YOUR_CHANNEL_ID_HERE",
    "SELENIUM_DRIVER": "chrome",
    "DRIVER_PATH": null,
    "RESPONSE_TIMEOUT": 60,
    "USE_PERSONAS": false
}
```

- `SILLYTAVERN_URL`: The URL where your SillyTavern is running
- `CHARACTER_NAME`: The name of the character to use in SillyTavern
- `DISCORD_CHANNEL_ID`: The ID of the Discord channel where the bot should respond
- `SELENIUM_DRIVER`: Which browser to use (chrome, edge, or firefox)
- `DRIVER_PATH`: Path to the WebDriver executable (leave as null if in PATH)
- `RESPONSE_TIMEOUT`: How long to wait for AI responses (in seconds)
- `USE_PERSONAS`: Whether to use SillyTavern personas for Discord users

## Usage

1. **Start SillyTavern**

Make sure SillyTavern is running and accessible at the URL specified in your config.

2. **Run the bot**

```bash
python bot.py
```

3. **Discord Commands**

The bot responds to the following commands:

- `!help` - Show help information
- `!reconnect` - Reconnect to SillyTavern
- `!character <name>` - Change to a different character

Regular messages in the configured channel will be sent to SillyTavern and responses will be sent back to Discord.

## Advanced Usage

### Using Personas

If you enable `USE_PERSONAS` in the config, the bot will attempt to use SillyTavern's persona feature to attribute messages to different users. 

1. In SillyTavern, create personas with the same names as your Discord users
2. Set `USE_PERSONAS` to `true` in config.json
3. The bot will automatically use `/persona Username` before each message

### Custom Persona Mapping

To map specific Discord user IDs to specific persona names, edit the `persona_mapping` dictionary in the `set_persona` method.

## Troubleshooting

- **Bot can't connect to SillyTavern**: Make sure SillyTavern is running and the URL in config.json is correct
- **Character not found**: Check that the character name matches exactly (case-sensitive)
- **WebDriver errors**: Ensure you have the correct WebDriver for your browser version
- **Slow responses**: Increase the `RESPONSE_TIMEOUT` value in config.json

## Limitations

- This bot uses web automation and may break if SillyTavern's interface changes
- Only one character can be active at a time
- The bot can only monitor one Discord channel
- Performance depends on your hardware and the AI backend you're using with SillyTavern

## License

This project is licensed under the MIT License - see the LICENSE file for details.

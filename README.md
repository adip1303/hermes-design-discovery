# Design Discovery for Hermes

**Lock in your design like a designer would, without needing to be one.**

Vibe coding makes building easy, but it assumes you can describe what you want. Most people can't say what they want a product to look like. They know it should feel "warm" or "not like every other AI tool", and stop there.

Design Discovery is a Hermes plugin that works like a design consultant for people who don't speak design. Hermes asks a few plain questions, shows you three visual directions built from your own words, lets you change what you don't like, and hands off a `DESIGN.md` that a coding agent can build from.

- **Chat is the consultant.** Hermes interviews you and explains tradeoffs in plain language. You make every change by saying it in chat.
- **The pane is where you see your options.** Three live specimens show type, color, spacing, shape and motion side by side, and the pane follows your choices as you make them.
- **The skill and data are the design brain.** A vocabulary of everyday words mapped to design moves, a curated font library, and conflict rules.
- **DESIGN.md is the handoff.** Real values, not vibes: tokens, a type scale, a contrast table, and the decisions you made.

## How it works

1. **Understand.** Hermes asks a few short questions: what you're making, who it's for, how it should feel, and what you don't want. It plays back what it heard and waits for you to confirm.
2. **Compose.** Hermes turns your words into three directions that differ in ways you can see and name: light or dark, warm or cool, which color leads, serif or sans.
3. **Refine.** Say what you'd change in your own words ("make the button orange, like a tangerine", "use the button color from option 2"). Hermes adjusts, keeps every color readable, and tells you when it had to shift one to get there. It never decides for you.
4. **Hand off.** When you're happy, Hermes exports `DESIGN.md`. Give it to Hermes, Claude Code, Codex or any coding agent.

## What makes it different

Most design tools for agents start from a brief. This one starts before the brief exists, for someone who can't write one yet.

- **Your words, not presets.** Directions are composed from a vocabulary of about 60 everyday words ("welcoming", "serious", "natural", "not generic SaaS"), not picked from a fixed set of themes.
- **You decide.** Nothing is locked, rejected or exported until you say so. The plugin checks that approvals came from you, not from the agent.
- **Honest about tradeoffs.** When choices pull against each other (dense but calm, playful but trustworthy), Hermes names the tension and how to resolve it. It warns; it never blocks.
- **Legible by construction.** Every palette is checked against WCAG contrast, and button text always meets 4.5:1.

## Install

Requires Hermes 0.23.0 or later.

From the Hermes plugin catalog, once it's listed:

```
hermes plugins install design-discovery
hermes plugins enable design-discovery
```

Or straight from GitHub:

```
hermes plugins install https://github.com/adip1303/hermes-design-discovery
```

Installing from GitHub gives you the latest commit rather than a reviewed version, and Hermes shows a warning for that.

Turning on the plugin also turns on its Desktop half. If the design pane doesn't appear, open Settings, Capabilities, Plugins and check that Design Discovery's Desktop switch is on. Restart Hermes Desktop after installing.

## Use

Start a new chat and run:

```
/design-discovery:design-discovery
```

Then describe what you're making, as vaguely as you like. For example:

> A dashboard for checking my agents every morning. I'm kinda bored of every AI tool looking the same, but I honestly don't know what else it could look like.

Open the design pane with **Open workbench** to see the directions.

**Models.** It works best on capable models. Weaker models trip more often: they may skip a step or call a tool wrongly, and Hermes usually recovers on the next call. Tested on GPT 6 Luna.

## Where DESIGN.md goes

- If you name a folder in chat, it goes there.
- Otherwise it goes to the chat's working folder, as long as that isn't your home folder, a drive root or Hermes's own folder.
- Otherwise it goes to `Documents\Design Discovery\`.

The file is named `DESIGN.md`. If that folder already has a `DESIGN.md` the plugin didn't write, it saves `DESIGN-<direction>.md` instead. It never overwrites a file it didn't write; exporting again from the same chat updates its own file. The pane has **Copy DESIGN.md**, **Copy path** and **Open folder**.

## What it doesn't do

- It doesn't build your product. During a design session, Hermes is limited to the design tools. Once `DESIGN.md` is exported, ask Hermes (or any coding agent) to build from it.
- It doesn't generate full page mockups or images. The pane shows compact specimens, enough to judge a direction.
- It isn't a design system editor or a Figma replacement.

## What it does on your machine

- **Network:** the pane and `DESIGN.md` load fonts from Google Fonts (`fonts.googleapis.com`). Offline, the pane falls back to system fonts. There are no other network calls and no telemetry. The design knowledge ships with the plugin.
- **Files it reads:** none outside its own data. When exporting, it only checks that the target folder exists; it never reads the files in it.
- **Files it writes:** session state in Hermes's plugin data folder, and `DESIGN.md` in the folder described above.
- **Your messages:** to check that approvals came from you, the plugin keeps up to the last 50 of your messages and 50 of Hermes's replies from a design chat, plus a log of up to 100 events, in that chat's session folder on your machine. Other chats are never written to disk.
- **Shell commands:** none. **Open folder** asks Hermes to show the folder.
- **Background activity:** no background processes. While the pane is open, it checks for updates every 1.5 seconds.
- **Credentials:** none stored.

## Built with

Designed by Adhip Arora, a product and industrial designer. Built with Codex and Claude.

## License

MIT. See `LICENSE`.

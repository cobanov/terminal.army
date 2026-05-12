# terminal.army

A multiplayer space strategy game you play from your terminal.

[![play at terminal.army](https://img.shields.io/badge/play-terminal.army-fbbf24)](https://terminal.army)

![hero](docs/screenshots/hero.png)


## What is this

`terminal.army` is a love letter to [OGame](https://ogame.fandom.com/wiki/OGame_Wiki), the legendary browser-based space strategy game from the early 2000s, rewritten in Python and played entirely through your terminal.

Build mines, research technology, train fleets, raid your friends, scout the galaxy with espionage probes, found alliances. Resources accrue in real time. Multiple players share the same universe.

Everything happens inside the terminal. There is no game client to download beyond a single Python package, no Flash, no JavaScript heavy game UI. Slash commands all the way down.

It is completely free. It is a fun project. I wanted to write OGame in Python and see how playable a pure terminal version of it would be. The answer turned out to be: very.


## Install and play

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install and run
uv tool install --python 3.12 "git+https://github.com/cobanov/space-galactic-tui.git"
tarmy
```

On first launch the CLI opens a browser URL for you to sign up at [terminal.army](https://terminal.army). Confirm the signup, return to the terminal, the TUI takes over.

No further config needed. The CLI defaults to `https://terminal.army`.

To update later:

```bash
tarmy --update
```


## How you play

You type slash commands. `/help` lists them all. The autocomplete popup suggests the next argument as soon as you press space.

A handful of the most common:

| command | what it does |
| --- | --- |
| `/planet` | read out the current planet (resources, energy, queue) |
| `/upgrade metal_mine` | build or upgrade a structure |
| `/research energy` | research a technology |
| `/ships build small_cargo 5` | queue ship production |
| `/defense build rocket_launcher 10` | queue defense structures |
| `/attack 4:128:6` | send an attack fleet (opens a ship picker if you don't pass counts) |
| `/transport 4:128:6 m=10000` | move metal to a friend |
| `/espionage 4:128:6` | scout a target with espionage probes |
| `/galaxy` | open the galaxy map (arrow keys page through systems and galaxies) |
| `/msg cobanov hello` | message another commander |
| `/alliance` | view your alliance roster (management lives on the web) |
| `/quest` | onboarding objectives |
| `/info crawler` | encyclopedia entry for a building, tech, ship, or defense |
| `/switch 2` | jump to another of your planets (number, code, or name) |

Most commands have short aliases: `/u`, `/r`, `/s`, `/atk`, `/spy`, `/tx`, `/lb`.


## Inspired by, not affiliated with

This is a fan project inspired by OGame. The formulas (mine production, research costs, fleet speeds, espionage info levels, combat) come from the [OGame Fandom Wiki](https://ogame.fandom.com/wiki/Formulas). The look and feel and game flow are intentional homage. OGame and all related trademarks belong to their respective owners (Gameforge). This project is not affiliated with or endorsed by them.

Free, no ads, no premium currency, no pay to win. If the server is up and you can install Python 3.12, you can play.


## Issues

[github.com/cobanov/space-galactic-tui/issues](https://github.com/cobanov/space-galactic-tui/issues)

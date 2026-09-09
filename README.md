# Flycast Homebrew tap

Install [Flycast](https://github.com/flyinghead/flycast) on macOS, for Apple Silicon and Intel:

Requires Homebrew 6.0.13 or newer. Run `brew update` if needed.

```sh
brew install --cask flyinghead/flycast/flycast
```

This installs the latest stable release packaged in this tap and removes quarantine
automatically.

## Master and dev builds

For newer fixes or experimental changes, choose one of these channels:

```sh
# Master
brew install --cask flyinghead/flycast/flycast@master

# Dev / nightly
brew install --cask flyinghead/flycast/flycast@dev
```

All channels install `Flycast.app` and share settings and saves. Uninstall your
current channel before switching, without `--zap`. For example:

```sh
brew uninstall --cask flyinghead/flycast/flycast
brew install --cask flyinghead/flycast/flycast@dev
```

## Update

```sh
brew update
brew upgrade --cask flyinghead/flycast/flycast
```

For master or dev, replace `flycast` with `flycast@master` or `flycast@dev` in the
last command. Development updates become available when this tap is updated.

## Uninstall

```sh
brew uninstall --cask flyinghead/flycast/flycast
```

Settings and saves are retained. Add `--zap` to also move `emu.cfg` settings files
from Flycast's standard data folders to the Trash. Saves, BIOS files, ROMs, and
controller mappings are preserved. Use your installed channel's name when removing
master or dev.

## Existing installations

If you installed Flycast from Homebrew's main tap, run `brew uninstall --cask flycast`
before installing from this tap. For a manually installed copy, move the existing
`Flycast.app` out of Applications first. Your settings and saves are retained.

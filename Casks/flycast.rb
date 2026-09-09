cask "flycast" do
  version "2.7"
  sha256 "dbd59cb88f52a95ea4de90693bb4ac156530452d5457f2cc4f656fdfd242fc26"

  url "https://github.com/flyinghead/flycast/releases/download/v#{version}/flycast-macOS-#{version}.zip"
  name "Flycast"
  desc "Dreamcast, Naomi, Naomi 2 and Atomiswave emulator"
  homepage "https://github.com/flyinghead/flycast"

  livecheck do
    url :url
    strategy :github_latest
  end

  depends_on :macos

  if ::Version.new(HOMEBREW_VERSION) < ::Version.new("6.0.13")
    raise "Flycast requires Homebrew 6.0.13 or newer. Run `brew update`, then retry installation."
  end

  app "Flycast.app"

  postflight_steps do
    run "/usr/bin/xattr",
        args: ["-dr", "com.apple.quarantine", "{{appdir}}/Flycast.app"]
  end

  # Keep saves, BIOS files and user-created controller mappings. Additional
  # macOS instances store their configuration in numbered subdirectories.
  zap trash: [
        "~/.flycast/[0-9]*/emu.cfg",
        "~/.flycast/emu.cfg",
        "~/Library/Application Support/Flycast/[0-9]*/emu.cfg",
        "~/Library/Application Support/Flycast/emu.cfg",
      ],
      rmdir: [
        "~/.flycast",
        "~/Library/Application Support/Flycast",
      ]
end

# BMO - GameBoy-style terminal (Python/tkinter)
#
# Install:
#   brew tap lmdelm-dev/tap https://github.com/lmdelm-dev/homebrew-tap
#   brew install bmo
#
# (The tap repo "homebrew-tap" just needs this Formula/ dir. Copy this file as
#  Formula/bmo.rb into github.com/lmdelm-dev/homebrew-tap and push.)
class Bmo < Formula
  desc "BMO - a GameBoy-style terminal (tkinter)"
  homepage "https://github.com/lmdelm-dev/bmo"
  url "https://github.com/lmdelm-dev/bmo/archive/refs/tags/v0.3.0.tar.gz"
  sha256 "5e3fefbd6b5dce5e8851b98ade242b67ff7b2b71e8f6668fdd28b262b45b3c45"
  license "MIT"

  depends_on "python@3.12"

  def install
    # Ship the Python app + assets to libexec
    libexec.install "gameboy.py", "assets"
    # Keep the repo launcher as-is for reference, but create a proper wrapper
    (bin/"bmo").write <<~EOS
      #!/bin/bash
      export BMO_HOME="#{libexec}"
      exec "#{Formula["python@3.12"].opt_bin}/python3" "#{libexec}/gameboy.py" "$@"
    EOS
    chmod 0755, bin/"bmo"

    # Desktop entry + icon for double-click
    (share/"applications").install "bmo.desktop"
    (share/"icons"/"hicolor"/"256x256"/"apps").install "assets/bmo-icon.png" => "bmo.png"
  end

  test do
    system "#{Formula["python@3.12"].opt_bin}/python3",
           "-m", "py_compile", "#{libexec}/gameboy.py"
  end
end

{
  description = "Python 3.10 Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11"; # Adjust based on your NixOS version
  };

  outputs = { self, nixpkgs }:
  let
    system = "x86_64-linux"; # Ensure we specify the system
    pkgs = nixpkgs.legacyPackages.${system};
  in {
    devShells.${system}.default = pkgs.mkShell {
      packages = [
        pkgs.python310  # Install Python 3.10
        pkgs.python310Packages.pip  # Include pip
        #pkgs.gcc
        #pkgs.jetbrains.pycharm-community-src
      ];

      shellHook = ''
        echo "Python 3.10 environment loaded!"
        python --version
      '';
    };
  };
}

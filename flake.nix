{
  description = "Hermes: System Test and Execution Platform";

  nixConfig = {
    extra-substituters = [ "https://tanged123.cachix.org" ];
    extra-trusted-public-keys = [
      "tanged123.cachix.org-1:S79iH77XKs7/Ap+z9oaafrhmrw6lQ21QDzxyNqg1UVI="
    ];
  };

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    treefmt-nix.url = "github:numtide/treefmt-nix";

    # Icarus simulation engine (provides Python bindings)
    icarus = {
      url = "github:tanged123/icarus";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      treefmt-nix,
      icarus,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # Get Icarus Python bindings
        # TODO: Change to icarus.packages.${system}.python once Icarus
        # implements nix_python_bindings.md plan
        icarusPython = icarus.packages.${system}.python or null;

        # Python environment with Hermes dependencies
        pythonEnv = pkgs.python3.withPackages (
          ps:
          [
            ps.websockets
            ps.pyyaml
            ps.pydantic
            ps.structlog
            ps.numpy
            ps.click
            # Testing
            ps.pytest
            ps.pytest-asyncio
            ps.pytest-cov
            # Dev tools
            ps.mypy
          ]
          ++ (if icarusPython != null then [ icarusPython ] else [ ])
        );

        # Treefmt configuration
        treefmtEval = treefmt-nix.lib.evalModule pkgs {
          projectRootFile = "flake.nix";
          programs.nixfmt.enable = true;
          programs.ruff-check.enable = true;
          programs.ruff-format.enable = true;
        };

        # Hermes package
        hermesPackage = pkgs.python3Packages.buildPythonPackage {
          pname = "hermes";
          version = "0.1.0";
          src = ./.;
          format = "pyproject";

          nativeBuildInputs = [
            pkgs.python3Packages.hatchling
          ];

          propagatedBuildInputs = [
            pkgs.python3Packages.websockets
            pkgs.python3Packages.pyyaml
            pkgs.python3Packages.pydantic
            pkgs.python3Packages.structlog
            pkgs.python3Packages.numpy
            pkgs.python3Packages.click
          ]
          ++ (if icarusPython != null then [ icarusPython ] else [ ]);

          doCheck = false; # Tests require Icarus at runtime
        };
      in
      {
        packages = {
          default = hermesPackage;
          hermes = hermesPackage;
        };

        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
            pkgs.ruff
            pkgs.doxygen
            pkgs.graphviz
            treefmtEval.config.build.wrapper
          ];

          shellHook = ''
            # Add local src to path for development
            export PYTHONPATH="$PWD/src:$PYTHONPATH"

            echo "Hermes dev environment loaded"
            ${
              if icarusPython != null then
                ''
                  echo "  - Icarus: available"
                ''
              else
                ''
                  echo "  - Icarus: NOT AVAILABLE (implement icarus nix_python_bindings.md)"
                ''
            }
            echo "  - Python: ${pythonEnv.python.version}"
          '';
        };

        formatter = treefmtEval.config.build.wrapper;

        checks = {
          formatting = treefmtEval.config.build.check self;
        };
      }
    );
}

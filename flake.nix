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

    # Icarus simulation engine
    icarus = {
      # For CI/production:
      # url = "github:tanged123/icarus";
      # For local development:
      url = "path:/home/tanged/sources/icarus";
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

        # Get Icarus package (includes Python bindings)
        icarusPackage = icarus.packages.${system}.default;

        # Python environment with Hermes dependencies + Icarus
        pythonEnv = pkgs.python3.withPackages (ps: [
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
        ]);

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
          ];

          # Icarus bindings are loaded at runtime
          makeWrapperArgs = [
            "--prefix PYTHONPATH : ${icarusPackage}/lib/python3.12/site-packages"
          ];

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
            icarusPackage
            pkgs.ruff
            treefmtEval.config.build.wrapper
          ];

          shellHook = ''
            # Add Icarus Python bindings to path
            export PYTHONPATH="${icarusPackage}/lib/python3.12/site-packages:$PYTHONPATH"

            # Add local src to path for development
            export PYTHONPATH="$PWD/src:$PYTHONPATH"

            echo "Hermes dev environment loaded"
            echo "  - Icarus: ${icarusPackage.version or "dev"}"
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

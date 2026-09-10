def pytest_addoption(parser):
    # `load_env()` reads --config from sys.argv; declare it so pytest passes it through.
    parser.addoption(
        "--config",
        action="append",
        default=[],
        help="Configuration file to load, may be given more than once.",
    )

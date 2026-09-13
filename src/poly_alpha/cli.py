"""Poly-Alpha CLI: quantitative strategy runner for prediction market alpha."""

from __future__ import annotations

import typer
from rich.console import Console

from poly_alpha.cli_platform import app as platform_app

app = typer.Typer(
    name="poly-alpha",
    help="Autonomous quantitative engine for prediction market alpha extraction.",
)
console = Console()

app.add_typer(platform_app, name="research")


@app.command()
def scan() -> None:
    """Scan active markets and display top alpha opportunities."""
    from poly_alpha.execution.paper_engine import deploy_trades

    deploy_trades()


@app.command()
def status() -> None:
    """Show current paper portfolio status."""
    from poly_alpha.execution.paper_engine import status as show_status

    show_status()


@app.command()
def init() -> None:
    """Initialize the paper wallet database."""
    from poly_alpha.execution.paper_engine import init_db

    init_db()


@app.command()
def step() -> None:
    """Run one full cycle: settle resolved trades, deploy new ones, show status."""
    from poly_alpha.execution.paper_engine import deploy_trades, settle_trades
    from poly_alpha.execution.paper_engine import status as show_status

    settle_trades()
    deploy_trades()
    show_status()


@app.command()
def live(capital: float = 1000.0) -> None:
    """Run live executor with risk filtering and CLOB sizing."""
    from poly_alpha.execution.live_executor import run

    run(capital=capital)


@app.command()
def backtest(
    engine: str = typer.Argument("empirical", help="Engine: 'empirical' or 'mc'"),
    iterations: int = typer.Option(10_000, help="Number of Monte Carlo iterations"),
) -> None:
    """Run backtesting engine."""
    if engine == "mc":
        from poly_alpha.backtesting.monte_carlo import run as mc_run

        mc_run(iterations=iterations)
    else:
        from poly_alpha.backtesting.empirical import run as emp_run

        emp_run(n_trials=iterations)


if __name__ == "__main__":
    app()

import click

@click.command()
@click.argument("BASE_COMMIT", default="HEAD^")
@click.argument("TARGET_COMMIT", default="HEAD")
def main(base_commit, target_commit) -> None:
    """Find bugs in code changes between two commits.
    """
    print("Buyacka! Welcome to RML!")

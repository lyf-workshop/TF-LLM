#!/usr/bin/env python3
"""Load the maintained Wordle practice template and print its runtime contract."""

from utu.config import ConfigLoader


def main() -> None:
    config = ConfigLoader.load_training_free_grpo_config(
        "korgym/TEMPLATE_wordle_practice"
    )
    game = config.runtime.korgym
    agent = config.runtime.agent
    print("=" * 60)
    print(f"exp_id: {config.exp_id}")
    print(f"practice_dataset: {config.data.practice_dataset_name}")
    print(f"runtime.korgym.game_name: {game.game_name}")
    print(f"runtime.korgym.game_port: {game.game_port}")
    print(f"runtime.agent: {agent.agent.name if agent is not None else None}")
    print("=" * 60)


if __name__ == "__main__":
    main()

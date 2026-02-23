from cub.formatting import format_task_list


def test_format_task_list_default_title() -> None:
    text = format_task_list(
        [
            {
                "id": "a1b2c3d4",
                "status": "queued",
                "label": "do thing",
                "created_at": 0.0,
            }
        ]
    )
    assert text.startswith("Recent tasks:\n")


def test_format_task_list_custom_title() -> None:
    text = format_task_list(
        [
            {
                "id": "a1b2c3d4",
                "status": "running",
                "label": "do thing",
                "created_at": 0.0,
            }
        ],
        title="Ongoing tasks:",
    )
    assert text.startswith("Ongoing tasks:\n")

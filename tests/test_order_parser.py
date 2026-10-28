from order_parser import detect_order_sets_and_quantity


def test_set1_and_set5_labels_are_recognized():
    assert detect_order_sets_and_quantity("SET1") == (1, 1)
    assert detect_order_sets_and_quantity("SET5") == (5, 1)
    assert detect_order_sets_and_quantity("SET 1") == (1, 1)
    assert detect_order_sets_and_quantity("SET 5") == (5, 1)


def test_set_label_quantity_is_preserved():
    assert detect_order_sets_and_quantity("SET1 x 2") == (1, 2)
    assert detect_order_sets_and_quantity("SET5 x 10") == (5, 10)


def test_legacy_russian_and_xp_formats_still_work():
    assert detect_order_sets_and_quantity("1 сет карточек Steam") == (1, 1)
    assert detect_order_sets_and_quantity("5 сетов карточек Steam") == (5, 1)
    assert detect_order_sets_and_quantity("25 карт Steam") == (5, 1)
    assert detect_order_sets_and_quantity("100 XP") == (1, 1)
    assert detect_order_sets_and_quantity("500 XP") == (5, 1)


def test_set_prefix_does_not_match_other_numbers():
    assert detect_order_sets_and_quantity("SET10") == (None, 1)
    assert detect_order_sets_and_quantity("SET50") == (None, 1)

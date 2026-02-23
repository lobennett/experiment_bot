from experiment_bot.platforms.base import Platform


def test_platform_is_abstract():
    try:
        Platform()
        assert False, "Should raise TypeError"
    except TypeError:
        pass


def test_platform_subclass_must_implement_methods():
    class Incomplete(Platform):
        pass
    try:
        Incomplete()
        assert False, "Should raise TypeError"
    except TypeError:
        pass

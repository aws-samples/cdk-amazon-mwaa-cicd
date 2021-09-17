"""We use this file as an example for some module."""


def hello(**kwargs):
    """
    Just an greetings example.

    :param kwargs:
        name (str): Name to greet.
    :Returns:
        str: greeting message
    """
    if kwargs.get("name"):
        print(f"Hello {kwargs['name']}!")
        return f"Hello {kwargs['name']}!"
    else:
        print(f"Hello Stranger")
        return f"Hello Stranger"


__all__ = ["hello"]

if __name__ == "__main__":
    hello()

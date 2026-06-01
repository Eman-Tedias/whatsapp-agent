from schemas import Session


def main():
    session = Session(session_id="local")
    print(session.step(""))
    while not session.done:
        text = input("Você: ").strip()
        print(session.step(text))


if __name__ == "__main__":
    main()

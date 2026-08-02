from config import ROUTER_MODE

if ROUTER_MODE == "agentic":
    from agentic.schemas import Session
else:
    from deterministic.schemas import Session


def main():
    session = Session(session_id="local")
    while not session.done:
        text = input("Você: ").strip()
        print(session.step(text))


if __name__ == "__main__":
    main()

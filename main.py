"""
AutoLab - Process orchestrator.
Launches all services: StreamElements bettors, Telegram webapp, and Discord bot.
"""
import multiprocessing

from dotenv import load_dotenv
load_dotenv()

if __name__ == "__main__":

    kill_event = multiprocessing.Event()

    from stream_elements.oauth import check_oauth_token
    OAUTH = {
        "el_pipow": check_oauth_token("El_Pipow"),
        "jrcosta": check_oauth_token("JRCosta"),
    }

    process_list = []

    from stream_elements.bettor import Bettor
    process_list.append(multiprocessing.Process(target=Bettor,
        args=("runah", "JRCosta", OAUTH["jrcosta"], kill_event)))
    process_list.append(multiprocessing.Process(target=Bettor,
        args=("runah", "El_Pipow", OAUTH["el_pipow"], kill_event, True)))
    process_list.append(multiprocessing.Process(target=Bettor,
        args=("prcs", "JRCosta", OAUTH["jrcosta"], kill_event, True)))
    process_list.append(multiprocessing.Process(target=Bettor,
        args=("prcs", "El_Pipow", OAUTH["el_pipow"], kill_event)))
    process_list.append(multiprocessing.Process(target=Bettor,
        args=("nopeej", "JRCosta", OAUTH["jrcosta"], kill_event, True)))
    process_list.append(multiprocessing.Process(target=Bettor,
        args=("nopeej", "El_Pipow", OAUTH["el_pipow"], kill_event)))
    process_list.append(multiprocessing.Process(target=Bettor,
        args=("valek", "JRCosta", OAUTH["jrcosta"], kill_event, True)))
    process_list.append(multiprocessing.Process(target=Bettor,
        args=("valek", "El_Pipow", OAUTH["el_pipow"], kill_event)))
    process_list.append(multiprocessing.Process(target=Bettor,
        args=("n0vaisj", "JRCosta", OAUTH["jrcosta"], kill_event, True)))
    process_list.append(multiprocessing.Process(target=Bettor,
        args=("n0vaisj", "El_Pipow", OAUTH["el_pipow"], kill_event)))
    process_list.append(multiprocessing.Process(target=Bettor,
        args=("windoh", "JRCosta", OAUTH["jrcosta"], kill_event, True)))
    process_list.append(multiprocessing.Process(target=Bettor,
        args=("windoh", "El_Pipow", OAUTH["el_pipow"], kill_event)))
    process_list.append(multiprocessing.Process(target=Bettor,
        args=("el_pipow", "JRCosta", OAUTH["jrcosta"], kill_event, True)))

    import webapp
    process_list.append(multiprocessing.Process(target=webapp.launch, args=()))

    from boost_bot.main import run_bot as run_discord_bot
    process_list.append(multiprocessing.Process(target=run_discord_bot, args=()))

    # from wallapop_tracker.tracker import term_func
    # process_list.append(multiprocessing.Process(target=term_func,
    #     args=("Pies de gato 42", None, 5, 60)))

    for process in process_list:
        process.start()

    try:
        while not kill_event.wait(0.5):
            pass
    except KeyboardInterrupt:
        kill_event.set()
        print("Shutdown signal received. Stopping all processes...")

    for process in process_list:
        process.join()
    print("All processes stopped gracefully.")

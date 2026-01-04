from colorama import Fore, Style, init

init(autoreset=True)



def log_info(message, toolname):
    print(f"{Fore.GREEN}[INFO]({toolname}){Style.RESET_ALL} {message}")

def log_warning(message, toolname):
    print(f"{Fore.BLUE}[WARNING]({toolname}){Style.RESET_ALL} {message}")

def log_error(message, toolname):
    print(f"{Fore.RED}[ERROR]({toolname}){Style.RESET_ALL} {message}")


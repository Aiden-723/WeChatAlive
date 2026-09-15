import argparse
from wechatauto import __version__


def main():
    parser = argparse.ArgumentParser(description="wechatauto 命令行工具")
    parser.add_argument('--version', '-v', action='store_true', help='显示版本信息')
    args = parser.parse_args()

    if args.version:
        print(f"wechatauto {__version__}")


if __name__ == '__main__':
    main()

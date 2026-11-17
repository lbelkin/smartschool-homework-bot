from connect_api import main


if __name__ == '__main__':
    print('API-only connection: no automated browser will be opened.')
    try:
        main()
    except (Exception, KeyboardInterrupt):
        print('Connection failed. Sensitive error details are not displayed.')
        raise SystemExit(1)

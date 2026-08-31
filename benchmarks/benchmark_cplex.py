from benchmark_commercial_smoke import main


if __name__ == "__main__":
    import sys
    sys.argv = [sys.argv[0], "cplex"]
    main()

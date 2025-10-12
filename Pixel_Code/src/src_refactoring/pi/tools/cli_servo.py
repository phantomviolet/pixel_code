import argparse, sys, time
from pi.control.esp32_link import open_from_config

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="pi/config.yaml")
    ap.add_argument("--ping", action="store_true")
    ap.add_argument("--stat", action="store_true")
    ap.add_argument("--deg", type=int)
    ap.add_argument("--us", type=int)
    ap.add_argument("--watch", action="store_true", help="ESP32 출력 실시간 보기 (포트 닫지 않음)")
    ap.add_argument("--port", help="override serial port")
    args = ap.parse_args()

    link = open_from_config(args.config)
    if args.port:
        link.ser.port = args.port
        link.ser.close(); link.ser.open()

    try:
        if args.ping:
            print(">> PING")
            print("<<", link.ping())
            # ✅ 포트 유지 모드
            if args.watch:
                print("[INFO] 포트를 닫지 않고 실시간 출력 유지 중 (Ctrl+C로 종료)")
                while True:
                    line = link.ser.readline().decode(errors="ignore").strip()
                    if line:
                        print(line)
                    time.sleep(0.05)

        if args.stat:
            print(">> GET_STAT")
            print("<<", link.get_stat())
        if args.deg is not None:
            print(f">> SET_DEG {args.deg}")
            print("<<", link.set_deg(args.deg))
        if args.us is not None:
            print(f">> SET_US {args.us}")
            print("<<", link.set_us(args.us))
        if not any([args.ping, args.stat, args.deg is not None, args.us is not None]):
            ap.print_help()

    except KeyboardInterrupt:
        print("\n[EXIT] user interrupted.")
    except Exception as e:
        print("[ERR]", e, file=sys.stderr)
    finally:
        pass  # 포트를 닫지 않음

if __name__ == "__main__":
    main()
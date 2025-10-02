from src.scooter.rplidar_front import RPLidar

class RPLidarFront:
    def __init__(self, port='/dev/ttyUSB0', front_deg=50):
        self.port = port
        self.front_deg = front_deg
        self.lidar = None

    def __enter__(self):
        self.lidar = RPLidar(self.port)
        self.lidar.start_motor()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.lidar.stop()
            self.lidar.stop_motor()
            self.lidar.disconnect()
        except:
            pass

    def iter_front_min(self):
        for scan in self.lidar.iter_scans(max_buf_meas=5000):
            vals = [d for q,a,d in scan if -self.front_deg <= a <= self.front_deg and d > 0]
            yield min(vals) if vals else None
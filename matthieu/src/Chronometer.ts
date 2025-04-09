export class Chronometer {
  private startTime: number = 0;

  start(): void {
    this.startTime = Date.now();
  }

  getElapsedTime(): number {
    return (Date.now() - this.startTime) / 1000;
  }

  getElapsedTimeFormatted(): string {
    return `${this.getElapsedTime().toFixed(2)}s`;
  }

  logTimeElapsedTime(): void {
    const elapsedTime = this.getElapsedTime();
    console.log(`[CHRONOMETER] ${elapsedTime.toFixed(2)} seconds`);
  }
}

export const WIDTH = 340;
export const HEIGHT = 260;
export const GAP = 12;

export function slots(area) {
    const rows = Math.max(0, Math.floor((area.height - GAP) / (HEIGHT + GAP)));
    const columns = Math.max(0, Math.floor((area.width - GAP) / (WIDTH + GAP)));
    const result = [];
    for (let column = 0; column < columns; column++) {
        for (let row = 0; row < rows; row++) {
            result.push({
                x: area.x + area.width - GAP - WIDTH - column * (WIDTH + GAP),
                y: area.y + GAP + row * (HEIGHT + GAP),
                width: WIDTH,
                height: HEIGHT,
            });
        }
    }
    return result;
}

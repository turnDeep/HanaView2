/**
 * A more robust lightweight-charts primitive for drawing a rectangle on the chart.
 * This version is based on official examples and best practices.
 */
class RectanglePrimitive {
    constructor(options) {
        this._options = options;
        this._source = null;
        this._x1 = null;
        this._y1 = null;
        this._x2 = null;
        this._y2 = null;
    }

    attached(source) {
        this._source = source;
    }

    detached() {
        this._source = null;
    }

    paneViews() {
        return [this];
    }

    updateAllViews() {
        if (!this._source) return;

        const { chart, series } = this._source;
        const timeScale = chart.timeScale();
        const priceScale = series.priceScale();

        const p1 = this._options.points[0];
        const p2 = this._options.points[1];

        // Convert time and price to canvas coordinates
        this._x1 = timeScale.timeToCoordinate(p1.time);
        this._y1 = priceScale.priceToCoordinate(p1.price);
        this._x2 = timeScale.timeToCoordinate(p2.time);
        this._y2 = priceScale.priceToCoordinate(p2.price);
    }

    renderer() {
        return this;
    }

    draw(target) {
        target.useBitmapCoordinateSpace(scope => {
            if (this._x1 === null || this._x2 === null || this._y1 === null || this._y2 === null) {
                return; // Don't draw if coordinates are not ready
            }
            const ctx = scope.context;
            const x = Math.min(this._x1, this._x2);
            const y = Math.min(this._y1, this._y2);
            const width = Math.abs(this._x1 - this._x2);
            const height = Math.abs(this._y1 - this._y2);

            // Draw the rectangle
            ctx.fillStyle = this._options.fillColor || 'rgba(255, 215, 0, 0.2)';
            ctx.fillRect(x, y, width, height);

            // Draw the border
            const borderWidth = this._options.borderWidth || 0;
            if (borderWidth > 0) {
                ctx.strokeStyle = this._options.borderColor || '#FFD700';
                ctx.lineWidth = borderWidth;
                ctx.strokeRect(x, y, width, height);
            }
        });
    }
}
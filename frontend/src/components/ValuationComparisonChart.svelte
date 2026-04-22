<script>
  import { onDestroy } from 'svelte';
  import { Chart, registerables } from 'chart.js';

  Chart.register(...registerables);

  export let dcf = 0;
  export let multiples = 0;
  export let intrinsicValue = 0;
  export let p10 = 0;
  export let p50 = 0;
  export let p90 = 0;
  export let unit = 'INR';

  let canvas;
  let chart;

  function renderChart() {
    if (!canvas) return;

    if (chart) {
      chart.destroy();
    }

    const divisor = unit === 'INR Crores' ? 1 : 1e7;
    const axisUnit = unit === 'INR Crores' ? 'Cr' : 'Cr (from INR)';

    chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: ['DCF', 'Multiples', 'Intrinsic', 'P10', 'P50', 'P90'],
        datasets: [
          {
            data: [dcf, multiples, intrinsicValue, p10, p50, p90].map((v) => Number(v) / divisor),
            backgroundColor: [
              'rgba(13, 110, 253, 0.75)',
              'rgba(108, 117, 125, 0.75)',
              'rgba(13, 148, 136, 0.75)',
              'rgba(220, 53, 69, 0.7)',
              'rgba(25, 135, 84, 0.75)',
              'rgba(255, 193, 7, 0.75)'
            ],
            borderWidth: 1
          }
        ]
      },
      options: {
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) =>
                `${ctx.label}: ${Number(ctx.parsed.y).toLocaleString('en-IN', { maximumFractionDigits: 2 })} ${axisUnit}`
            }
          }
        },
        scales: {
          y: {
            title: { display: true, text: `Value (${axisUnit})` },
            ticks: {
              callback: (value) => Number(value).toLocaleString('en-IN', { maximumFractionDigits: 1 })
            }
          }
        }
      }
    });
  }

  $: if (canvas) {
    renderChart();
  }

  onDestroy(() => {
    if (chart) chart.destroy();
  });
</script>

<div class="chart-wrapper">
  <canvas bind:this={canvas}></canvas>
</div>

<style>
  .chart-wrapper {
    height: 300px;
    width: 100%;
  }
</style>

<script>
  import { onDestroy } from 'svelte';
  import { Chart, registerables } from 'chart.js';

  Chart.register(...registerables);

  export let histogram = [];
  export let unit = 'INR';

  let canvas;
  let chart;

  function renderChart() {
    if (!canvas || !histogram || histogram.length === 0) return;

    if (chart) {
      chart.destroy();
    }

    const divisor = unit === 'INR Crores' ? 1 : 1e7;
    const axisUnit = unit === 'INR Crores' ? 'Cr' : 'Cr (from INR)';
    const labels = histogram.map((bin) => {
      const mid = (Number(bin.bin_start) + Number(bin.bin_end)) / 2;
      const scaled = mid / divisor;
      return Number(scaled).toLocaleString('en-IN', { maximumFractionDigits: 1 });
    });
    const values = histogram.map((bin) => bin.count);

    chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            data: values,
            backgroundColor: 'rgba(32, 201, 151, 0.55)',
            borderColor: 'rgba(32, 201, 151, 0.95)',
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
              title: (items) => `Valuation ~ ${items[0]?.label || ''} ${axisUnit}`
            }
          }
        },
        scales: {
          x: {
            title: { display: true, text: `Valuation (${axisUnit})` },
            ticks: { maxTicksLimit: 8 }
          },
          y: {
            title: { display: true, text: 'Frequency' }
          }
        }
      }
    });
  }

  $: if (histogram && canvas) {
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

<script>
  import { onDestroy } from 'svelte';
  import { Chart, registerables } from 'chart.js';

  Chart.register(...registerables);

  export let forecast = [];
  export let unit = 'INR';

  let canvas;
  let chart;

  function renderChart() {
    if (!canvas || !forecast || forecast.length === 0) return;

    if (chart) {
      chart.destroy();
    }

    const labels = forecast.map((point) => String(point.year).slice(0, 4));
    const divisor = unit === 'INR Crores' ? 1 : 1e7;
    const axisUnit = unit === 'INR Crores' ? 'Cr' : 'Cr (from INR)';
    const mean = forecast.map((point) => Number(point.fcf_mean) / divisor);
    const upper = forecast.map((point) => Number(point.fcf_upper) / divisor);
    const lower = forecast.map((point) => Number(point.fcf_lower) / divisor);

    chart = new Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'FCF Mean',
            data: mean,
            borderColor: '#146c43',
            backgroundColor: 'rgba(20, 108, 67, 0.2)',
            borderWidth: 2,
            tension: 0.3
          },
          {
            label: 'FCF Upper',
            data: upper,
            borderColor: 'rgba(25, 135, 84, 0.65)',
            borderDash: [5, 5],
            borderWidth: 1.5,
            tension: 0.25
          },
          {
            label: 'FCF Lower',
            data: lower,
            borderColor: 'rgba(13, 110, 253, 0.6)',
            borderDash: [5, 5],
            borderWidth: 1.5,
            tension: 0.25
          }
        ]
      },
      options: {
        maintainAspectRatio: false,
        scales: {
          y: {
            title: { display: true, text: `FCF (${axisUnit})` },
            ticks: {
              callback: (value) => Number(value).toLocaleString('en-IN', { maximumFractionDigits: 1 })
            }
          }
        }
      }
    });
  }

  $: if (forecast && canvas) {
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

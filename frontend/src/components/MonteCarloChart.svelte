<script>
  import { onMount, onDestroy } from 'svelte';
  import { Chart, registerables } from 'chart.js';
  
  let { data } = $props(); 
  
  Chart.register(...registerables);
  Chart.defaults.color = '#71717a'; 
  Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
  Chart.defaults.font.size = 10;
  
  let canvas = $state();
  let chart;
  
  const initChart = () => {
    if (!canvas || !data?.monte_carlo) return;
    if (chart) chart.destroy();
    
    const p50 = data.monte_carlo.p50 || 100;
    const p10 = data.monte_carlo.p10 || (p50 * 0.8);
    const p90 = data.monte_carlo.p90 || (p50 * 1.2);
    const stdDev = (p90 - p10) / 2.56; 
    
    const labels = [];
    const distData = [];
    for (let i = -3; i <= 3; i += 0.15) {
      const x = p50 + (i * stdDev);
      const y = Math.exp(-0.5 * Math.pow((x - p50) / stdDev, 2)) / (stdDev * Math.sqrt(2 * Math.PI));
      labels.push((x / 1e9).toFixed(1) + 'B'); 
      distData.push(y);
    }
    
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 350);
    gradient.addColorStop(0, 'rgba(34, 211, 238, 0.2)'); 
    gradient.addColorStop(1, 'rgba(34, 211, 238, 0.00)'); 
    
    chart = new Chart(canvas, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'Probability Density',
          data: distData,
          borderColor: '#22d3ee', 
          borderWidth: 1.5,
          backgroundColor: gradient,
          fill: true,
          tension: 0.5,
          pointRadius: 0,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
        },
        scales: {
          x: { 
            grid: { color: 'rgba(255,255,255,0.02)', drawBorder: false }, 
            ticks: { maxTicksLimit: 6 } 
          },
          y: { grid: { display: false }, ticks: { display: false }, border: {display: false} }
        }
      }
    });
  };

  $effect(() => {
    if (data && canvas) {
      initChart();
    }
  });

  onDestroy(() => { if (chart) chart.destroy(); });
</script>

<div class="h-full w-full relative z-10">
  <canvas bind:this={canvas}></canvas>
</div>

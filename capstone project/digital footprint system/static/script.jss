<script>
const score = Number("{{ score }}");
const remaining = 8 - score;

new Chart(document.getElementById('riskChart'), {
    type: 'doughnut',

    data: {
        labels: ['Risk Score', 'Remaining Score'],
        datasets: [{
            data: [score, remaining],
            backgroundColor: [
                '#a855f7',
                '#26334d'
            ],
            borderColor: '#0f172a',
            borderWidth: 5,
            hoverOffset: 12
        }]
    },

    options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '72%',

        plugins: {
            legend: {
                position: 'bottom',
                labels: {
                    color: '#ffffff',
                    padding: 20,
                    font: {
                        size: 14
                    }
                }
            }
        }
    }
});
</script>
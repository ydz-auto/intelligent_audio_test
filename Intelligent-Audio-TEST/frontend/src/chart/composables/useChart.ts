import { ref, watch, nextTick, Ref } from 'vue';
import { Chart, ChartConfiguration } from 'chart.js/auto';
import zoomPlugin from 'chartjs-plugin-zoom';
import { getDefaultChartConfig, applyChartTypeConfig, mergeUserOptions, prepareChartData, calculateDistributionStats, calculateDistributionStatsByDevice, rebinDistributionData, DistributionStat } from '../utils/chartConfig';

Chart.register(zoomPlugin);

export const useChart = (props: any, emit: any, chartCanvas: Ref<HTMLCanvasElement | null>) => {
  const chart = ref<any>(null);
  const animationFrameId = ref<number | null>(null);
  const isMounted = ref(true);
  const hasData = ref(false);
  const distributionStats = ref<DistributionStat[]>([]);
  const distributionStatsByDevice = ref<{ [device: string]: DistributionStat[] }>({});

  const handleRetry = (retryCount: number, maxRetries = 3) => {
    if (retryCount < maxRetries) {
      retryCount++;
      setTimeout(() => {
        initChart(retryCount);
      }, 500);
    } else {
      console.error('Failed to initialize chart after 3 attempts');
    }
  };

  const destroyChart = () => {
    if (!chart.value) return;
    
    try {
      const canvas = chart.value.canvas;
      
      if (animationFrameId.value) {
        clearTimeout(animationFrameId.value);
        animationFrameId.value = null;
      }
      
      if (chart.value.stop) {
        chart.value.stop();
      }
      
      if (canvas && canvas instanceof HTMLCanvasElement && canvas.isConnected) {
        const mouseupEvent = new MouseEvent('mouseup', {
          bubbles: true,
          cancelable: true,
          view: window,
          clientX: 0,
          clientY: 0
        });
        const mouseleaveEvent = new MouseEvent('mouseleave', {
          bubbles: true,
          cancelable: true,
          view: window
        });
        
        canvas.dispatchEvent(mouseupEvent);
        canvas.dispatchEvent(mouseleaveEvent);
      }
      
      if (chart.value.options) {
        chart.value.options.events = [];
        if (chart.value.options.plugins && chart.value.options.plugins.zoom) {
          delete chart.value.options.plugins.zoom;
        }
      }
      
      if (chart.value._eventListeners) {
        chart.value._eventListeners.forEach((removeListener: () => void) => {
          try {
            removeListener();
          } catch (e) {
          }
        });
        delete chart.value._eventListeners;
      }
      
      chart.value.destroyed = true;
      chart.value.destroy();
      chart.value = null;
    } catch (destroyError) {
      console.warn('Error destroying chart during init:', destroyError);
    } finally {
      chart.value = null;
    }
  };

  const updateDataStatus = () => {
    hasData.value = !!(props.data && props.data.datasets && 
      props.data.datasets.some((dataset: any) => dataset.data && dataset.data.length > 0));
    
    if (props.type === 'distribution' && hasData.value) {
      distributionStats.value = calculateDistributionStats(props.data);
      distributionStatsByDevice.value = calculateDistributionStatsByDevice(props.data);
    } else {
      distributionStats.value = [];
      distributionStatsByDevice.value = {};
    }
  };

  const initChart = (retryCount = 0) => {
    if (!isMounted.value) {
      return;
    }
    
    if (!chartCanvas.value || !(chartCanvas.value instanceof HTMLCanvasElement)) {
      console.warn('Chart canvas element not found or invalid type:', chartCanvas.value);
      handleRetry(retryCount);
      return;
    }
    
    if (!chartCanvas.value.isConnected) {
      console.warn('Chart canvas element is not connected to DOM');
      handleRetry(retryCount);
      return;
    }
    
    const currentCanvas = chartCanvas.value;
    destroyChart();
    
    if (!currentCanvas || !(currentCanvas instanceof HTMLCanvasElement) || !currentCanvas.isConnected) {
      console.warn('Canvas element became invalid after cleanup');
      handleRetry(retryCount);
      return;
    }
    
    const canvas = chartCanvas.value;
    let ctx;
    try {
      ctx = canvas.getContext('2d');
      if (!ctx) {
        console.warn('Failed to get canvas context');
        handleRetry(retryCount);
        return;
      }
    } catch (error) {
      console.warn('Error getting canvas context:', error);
      handleRetry(retryCount);
      return;
    }
    
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    const chartType = props.type === 'distribution' ? 'line' : props.type;
    let defaultOptions = getDefaultChartConfig();
    defaultOptions = applyChartTypeConfig(defaultOptions, props.type, props.title);
    const chartOptions = mergeUserOptions(defaultOptions, props.options, props.type, props.enableZoom);
    
    chartOptions.animation = { duration: 0 };
    
    const chartData = prepareChartData(props.data, props.type);
    
    try {
      const chartConfig: ChartConfiguration = {
        type: chartType,
        data: chartData,
        options: chartOptions,
        plugins: []
      };
      
      chart.value = new Chart(ctx, chartConfig);
      
      if (chart.value) {
        chart.value.destroyed = false;
        
        const originalUpdate = chart.value.update;
        chart.value.update = function(this: any) {
          if (this.destroyed || !this.canvas || !this.canvas.isConnected || !this.ctx) {
            console.warn('Chart is destroyed or invalid, skipping update');
            return;
          }
          return originalUpdate.apply(this, arguments as any);
        };
        
        console.log('Chart created successfully');

        // 正态分布图：监听zoom事件，在可见范围内重新分箱统计
        if (props.type === 'distribution' && chart.value.options?.plugins?.zoom) {
          const onZoomComplete = () => {
            if (!chart.value || chart.value.destroyed) return;

            const xScale = chart.value.scales?.x;
            if (!xScale) return;

            const visibleMin = xScale.min;
            const visibleMax = xScale.max;
            if (visibleMin === undefined || visibleMax === undefined) return;

            // 重新分箱
            const newDatasets = rebinDistributionData(props.data, visibleMin, visibleMax);
            if (newDatasets && newDatasets.length > 0) {
              chart.value.data.datasets = newDatasets;
              chart.value.update('none');
            }
          };

          // chartjs-plugin-zoom 的 zoom/pan 完成事件
          chart.value.options.plugins.zoom.onZoomComplete = onZoomComplete;
          chart.value.options.plugins.zoom.onPanComplete = onZoomComplete;
        }

        if (chartType === 'line' || chartType === 'bar') {
          const chartCanvasEl = chart.value.canvas;
          if (chartCanvasEl && chartCanvasEl.isConnected) {
            const handleWheel = (event: WheelEvent) => {
              if (!chart.value || !chart.value.canvas || !chart.value.canvas.isConnected || !chart.value.canvas.parentNode) {
                return;
              }
              
              if (chart.value.destroyed) {
                return;
              }
              
              const rect = chartCanvasEl.getBoundingClientRect();
              const mouseX = event.clientX - rect.left;
              const mouseY = event.clientY - rect.top;
              
              if (mouseX >= 0 && mouseX <= rect.width && mouseY >= 0 && mouseY <= rect.height) {
                if (chart.value.chartArea && mouseX < chart.value.chartArea.left && chart.value.options?.plugins?.zoom) {
                  chart.value.options.plugins.zoom.zoom.mode = 'xy';
                } else if (chart.value.options?.plugins?.zoom) {
                  chart.value.options.plugins.zoom.zoom.mode = 'x';
                }
              } else {
                event.preventDefault();
                event.stopPropagation();
                return;
              }
            };
            
            const handleMouseMove = (event: MouseEvent) => {
              if (!chart.value || !chart.value.canvas || !chart.value.canvas.isConnected) {
                return;
              }
              
              const rect = chartCanvasEl.getBoundingClientRect();
              const mouseX = event.clientX - rect.left;
              const chartArea = chart.value.chartArea;
              
              if (chartArea && mouseX < chartArea.left && chart.value.options?.plugins?.zoom) {
                chart.value.options.plugins.zoom.zoom.mode = 'xy';
              } else if (chart.value.options?.plugins?.zoom) {
                chart.value.options.plugins.zoom.zoom.mode = 'x';
              }
            };
            
            chartCanvasEl.addEventListener('mousemove', handleMouseMove);
            chartCanvasEl.addEventListener('wheel', handleWheel, { passive: false });
            
            if (!chart.value._eventListeners) {
              chart.value._eventListeners = [];
            }
            chart.value._eventListeners.push(() => {
              try {
                if (chartCanvasEl && chartCanvasEl.isConnected) {
                  chartCanvasEl.removeEventListener('mousemove', handleMouseMove);
                  chartCanvasEl.removeEventListener('wheel', handleWheel);
                }
              } catch (e) {
              }
            });
          }
        }
        
        animationFrameId.value = window.setTimeout(() => {
          if (chart.value && chart.value.options) {
            try {
              chart.value.options.animation = getDefaultChartConfig().animation;
            } catch (error) {
              console.warn('Error updating chart animation options:', error);
            }
          }
          animationFrameId.value = null;
        }, 0);
        
        emit('chart-ready', chart.value);
      }
    } catch (error) {
      console.warn('Error creating chart:', error);
      chart.value = null;
    }
  };

  const resetZoom = () => {
    if (!chart.value || !chart.value.canvas || !chart.value.canvas.isConnected) {
      console.warn('Chart canvas not found or detached from DOM, cannot reset zoom');
      return;
    }
    
    try {
      if (chart.value.destroyed) {
        console.warn('Chart instance has been destroyed, cannot reset zoom');
        return;
      }
      
      if (chart.value.resetZoom) {
        chart.value.resetZoom();
      } else {
        if (chart.value.options && chart.value.options.scales) {
          Object.values(chart.value.options.scales).forEach((scale: any) => {
            if (scale) {
              scale.min = undefined;
              scale.max = undefined;
            }
          });
        }
        chart.value.update();
      }
    } catch (error) {
      console.warn('Error resetting zoom:', error);
    }
  };

  const exportChart = () => {
    if (chart.value) {
      const url = chart.value.toBase64Image();
      const link = document.createElement('a');
      link.href = url;
      link.download = `${props.title || 'chart'}.png`;
      link.click();
      emit('export', url);
    }
  };

  watch(() => props.data, () => {
    nextTick(() => {
      if (chartCanvas.value && chartCanvas.value.isConnected) {
        initChart();
      }
    });
  }, { deep: true });

  watch(() => props.type, () => {
    nextTick(() => {
      if (chartCanvas.value && chartCanvas.value.isConnected) {
        initChart();
      }
    });
  });

  watch(() => props.loading, () => {
    if (!props.loading) {
      nextTick(() => {
        if (chartCanvas.value && chartCanvas.value.isConnected) {
          initChart();
        }
      });
    }
  });

  watch(() => props.enableZoom, () => {
    nextTick(() => {
      if (chartCanvas.value && chartCanvas.value.isConnected) {
        initChart();
      }
    });
  });

  const mountChart = () => {
    nextTick(() => {
      initChart();
    });
  };

  const unmountChart = () => {
    isMounted.value = false;
    if (animationFrameId.value) {
      clearTimeout(animationFrameId.value);
      animationFrameId.value = null;
    }
    destroyChart();
  };

  updateDataStatus();

  watch(() => props.data, updateDataStatus, { deep: true });
  watch(() => props.type, updateDataStatus);

  return { chart, hasData, distributionStats, distributionStatsByDevice, initChart, resetZoom, exportChart, mountChart, unmountChart };
};

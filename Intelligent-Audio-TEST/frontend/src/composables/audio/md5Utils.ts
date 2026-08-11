import SparkMD5 from 'spark-md5';

/**
 * 计算文件的 MD5 哈希值（分片读取，避免大文件内存溢出）
 */
export async function calculateMd5(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunkSize = 10 * 1024 * 1024;
    const chunks = Math.ceil(file.size / chunkSize);
    const spark = new SparkMD5.ArrayBuffer();
    const reader = new FileReader();
    let currentChunk = 0;

    reader.onload = (e) => {
      if (e.target?.result) {
        spark.append(e.target.result as ArrayBuffer);
        currentChunk++;
        if (currentChunk < chunks) {
          loadNext();
        } else {
          resolve(spark.end());
        }
      }
    };

    reader.onerror = () => reject('MD5 calculation failed');

    function loadNext() {
      const start = currentChunk * chunkSize;
      const end = Math.min(start + chunkSize, file.size);
      reader.readAsArrayBuffer(file.slice(start, end));
    }

    loadNext();
  });
}

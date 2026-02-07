/**
 * MengLaService 用于处理缓存相关的服务逻辑。
 * 接收缓存器，按请求 id 进行 get/put/delete，并封装 query、updateData 等业务方法。
 */

/** 带超时的 fetch，兼容标准 RequestInit 并支持 timeout（毫秒） */
async function fetchWithTimeout(
  url: string,
  options: RequestInit & { timeout?: number } = {}
): Promise<Response> {
  const { timeout = 30000, ...init } = options
  const controller = new AbortController()
  const id = setTimeout(() => controller.abort(), timeout)
  try {
    const res = await fetch(url, { ...init, signal: controller.signal })
    return res
  } finally {
    clearTimeout(id)
  }
}

/** 按请求 id 存取的缓存器接口 */
export interface MengLaCacheAdapter<T = unknown> {
  get(reqId: string): T | undefined | Promise<T | undefined>
  put(reqId: string, value: T): void | Promise<void>
  delete(reqId: string): void | Promise<void>
}

/** query 方法的参数 */
export interface MengLaQueryParams {
  action: 'order' | 'chance' | 'high' | 'hot' | 'industryViewV2' | 'industryTrendRange'
  product_id?: string
  catId?: string
  dateType?: string
  timest?: string
  starRange?: string
  endRange?: string
  [key: string]: unknown
}

/**
 * 封装缓存与请求维度的查询、更新逻辑。
 * 缓存器由外部注入，支持内存 Map、Redis 等实现。
 */
export class MengLaService<T = unknown> {
  private lastRequestTime = 0
  private readonly MIN_REQUEST_INTERVAL = 5000 // 5秒间隔

  constructor(private readonly cache: MengLaCacheAdapter<T>) {}

  /**
   * 等待请求间隔
   */
  private async waitForRequestInterval(): Promise<void> {
    const now = Date.now()
    const timeSinceLastRequest = now - this.lastRequestTime
    
    if (timeSinceLastRequest < this.MIN_REQUEST_INTERVAL) {
      const waitTime = this.MIN_REQUEST_INTERVAL - timeSinceLastRequest
      await new Promise((resolve) => setTimeout(resolve, waitTime))
    }
    
    this.lastRequestTime = Date.now()
  }

  private async _requestMengla(params: MengLaQueryParams): Promise<string> {
    // 等待请求间隔
    await this.waitForRequestInterval()

    const baseUrl = process.env.COLLECT_SERVICE_URL || 'https://extract.b.nps.qzsyzn.com'
    const apiKey = process.env.COLLECT_SERVICE_API_KEY
    if (!apiKey) throw new Error('COLLECT_SERVICE_API_KEY environment variable is required')

    // 获取托管任务列表（直接请求采集服务 API）
    const listRes = await fetchWithTimeout(
      `${baseUrl}/api/managed-tasks?page=1&limit=100`,
      {
        headers: { Authorization: `Bearer ${apiKey}` },
        timeout: 15000,
      }
    )
    if (!listRes.ok) {
      throw new Error(`获取托管任务列表失败: ${listRes.status} ${await listRes.text()}`)
    }
    const managedTasks = (await listRes.json()) as { data?: { tasks?: Array<{ id: string; name: string }> } }

    if (!managedTasks?.data?.tasks) {
      throw new Error('获取托管任务列表失败: 响应格式异常')
    }

    // 打印所有任务名称用于调试
    console.log('可用的托管任务列表:', managedTasks.data.tasks.map(t => t.name))

    // 查找萌啦数据采集任务
    const collectTypeId = managedTasks.data.tasks.find(
      (task) => task.name === '萌啦数据采集'
    )?.id

    if (!collectTypeId) {
      const availableNames = managedTasks.data.tasks.map(t => t.name).join(', ')
      throw new Error(`未找到"萌啦数据采集"任务。可用任务: ${availableNames}`)
    }

    console.log('找到萌啦采集任务ID:', collectTypeId)

    // 构建请求参数
    const requestParams = {
      module: params.action,
      product_id: params.product_id || '',
      catId: params.catId || '',
      dateType: params.dateType || '',
      timest: params.timest || '',
      starRange: params.starRange || '',
      endRange: params.endRange || '',
    }

    // 获取 webhook URL
    const webhookUrl = `${process.env.APP_BASEURL}/api/webhook/mengla-notify`
    console.log('🔔 Webhook URL:', webhookUrl)

    const requestBody = {
      parameters: requestParams,
      webhookUrl: webhookUrl,
    }

    console.log('📤 发送采集请求:', {
      url: `${baseUrl}/api/managed-tasks/${collectTypeId}/execute`,
      body: requestBody,
    })

    try {
      const response = await fetchWithTimeout(
        `${baseUrl}/api/managed-tasks/${collectTypeId}/execute`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${apiKey}`,
          },
          body: JSON.stringify(requestBody),
          timeout: 30000,
        }
      )

      console.log('📥 响应状态:', response.status, response.statusText)

      if (!response.ok) {
        const errorText = await response.text()
        console.error('❌ 采集请求失败:', response.status, errorText)
        throw new Error(`采集请求失败: ${response.status} - ${errorText}`)
      }

      const responseText = await response.text()
      console.log('✅ 采集请求原始响应:', responseText)
      console.log('✅ 响应长度:', responseText.length, 'bytes')
      
      // 检查响应是否为空
      if (!responseText || responseText.trim() === '') {
        console.error('❌ 响应为空')
        throw new Error('采集请求失败: 服务器返回空响应')
      }
      
      let result: any
      try {
        result = JSON.parse(responseText)
        console.log('✅ 解析后的响应:', JSON.stringify(result, null, 2))
      } catch (parseError) {
        console.error('❌ JSON 解析失败:', parseError)
        console.error('❌ 原始响应内容:', responseText)
        throw new Error(`JSON 解析失败: ${responseText.substring(0, 200)}`)
      }

      if (!result.data?.executionId) {
        console.error('❌ 响应中没有 executionId:', result)
        throw new Error('采集请求失败，未返回 executionId')
      }

      const executionId = result.data.executionId
      console.log('🆔 获得 executionId:', executionId)
      console.log('⏳ 等待 webhook 回调到:', webhookUrl)
      console.log('💾 缓存实例 ID:', (this.cache as any).__instanceId__ || 'unknown')

      return executionId
    } catch (error) {
      console.error('❌ 采集请求失败:', error)
      throw error
    }
  }

  /**
   * 生成缓存键
   */
  private generateCacheKey(params: MengLaQueryParams): string {
    return JSON.stringify({
      action: params.action,
      product_id: params.product_id || '',
      catId: params.catId || '',
      dateType: params.dateType || '',
      timest: params.timest || '',
      starRange: params.starRange || '',
      endRange: params.endRange || '',
    })
  }

  /**
   * 按参数发起查询（可在此内组合调用 API/DB，并将结果按 reqId 写入缓存）。
   * @param params 查询参数，可包含 reqId 等
   * @param useCache 是否使用缓存，默认 true
   * @returns 查询结果，具体类型由子类或调用方约定
   */
  async query(params: MengLaQueryParams, useCache = true): Promise<unknown> {
    // 生成缓存键
    const cacheKey = this.generateCacheKey(params)
    
    // 如果启用缓存，先检查缓存中是否有数据
    if (useCache) {
      const cachedData = await this.cache.get(cacheKey)
      if (cachedData !== undefined) {
        console.log('从缓存中获取数据:', cacheKey)
        return cachedData
      }
    }

    console.log('缓存中无数据，发起新请求:', cacheKey)
    
    // 发起新的请求
    const reqId = await this._requestMengla(params)
    const timeoutMs = 30_000 // 增加超时时间到30秒
    let timeoutHandle: NodeJS.Timeout | null = null
    let timedOut = false

    console.log('⏳ 开始轮询缓存，等待 webhook 回调...')
    console.log('⏳ 轮询 executionId:', reqId)

    // 用 Promise.race 实现超时
    const result = await Promise.race([
      (async () => {
        let pollCount = 0
        while (true) {
          pollCount++
          const data = await this.cache.get(reqId)
          
          if (pollCount % 10 === 0) {
            console.log(`⏳ 已轮询 ${pollCount} 次，仍在等待 webhook 回调...`)
          }
          
          if (data !== undefined) {
            if (timeoutHandle) clearTimeout(timeoutHandle)
            console.log('✅ 收到 webhook 数据！')
            console.log('✅ 数据内容:', JSON.stringify(data).substring(0, 500))
            // 将数据也存入参数缓存键中
            await this.cache.put(cacheKey, data)
            return data
          }
          await new Promise((resolve) => setTimeout(resolve, 100))
          if (timedOut) break
        }
        return undefined
      })(),
      new Promise((_, reject) => {
        timeoutHandle = setTimeout(() => {
          timedOut = true
          console.error('❌ 查询超时（30秒），webhook 可能没有被调用')
          reject(new Error('查询超时（30秒）'))
        }, timeoutMs)
      }),
    ])

    return result
  }

  /**
   * 根据请求 id 更新数据（如从缓存取出后写回或触发持久化）。
   * @param reqId 请求 id
   * @returns 更新后的数据或是否成功，由实现决定
   */
  async updateData(reqId: string, data: unknown): Promise<unknown> {
    console.log('💾 更新缓存数据 - executionId:', reqId)
    console.log('💾 缓存实例 ID:', (this.cache as any).__instanceId__ || 'unknown')
    console.log('💾 数据大小:', JSON.stringify(data).length, 'bytes')
    await this.cache.put(reqId, data as T)
    
    // 验证数据是否真的存入了
    const verified = await this.cache.get(reqId)
    console.log('✅ 缓存验证:', verified !== undefined ? '成功' : '失败')
    
    return data
  }

  /**
   * 清除缓存
   * @param params 可选，指定要清除的参数缓存，不传则清除所有
   */
  async clearCache(params?: MengLaQueryParams): Promise<void> {
    if (params) {
      const cacheKey = this.generateCacheKey(params)
      await this.cache.delete(cacheKey)
      console.log('清除指定缓存:', cacheKey)
    } else {
      // 清除所有缓存（需要缓存器支持）
      console.log('清除所有缓存')
    }
  }
}

//实现一个基于内存的缓存器
export class MemoryMengLaCacheAdapter implements MengLaCacheAdapter {
  private readonly cache: Map<string, unknown> = new Map()
  private readonly __instanceId__: string
  
  constructor() {
    this.__instanceId__ = `cache-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    console.log('🆕 创建新的缓存实例:', this.__instanceId__)
  }
  
  get(reqId: string): unknown {
    const value = this.cache.get(reqId)
    console.log(`🔍 [${this.__instanceId__}] 读取缓存:`, reqId, '→', value !== undefined ? '命中' : '未命中')
    return value
  }
  put(reqId: string, value: unknown): void {
    console.log(`💾 [${this.__instanceId__}] 写入缓存:`, reqId)
    this.cache.set(reqId, value)
    console.log(`📊 [${this.__instanceId__}] 当前缓存大小:`, this.cache.size)
  }
  delete(reqId: string): void {
    console.log(`🗑️ [${this.__instanceId__}] 删除缓存:`, reqId)
    this.cache.delete(reqId)
  }
  
  // 调试方法：列出所有缓存键
  getAllKeys(): string[] {
    return Array.from(this.cache.keys())
  }
}

// 保证全局唯一的 menglaService 实例（单例模式）
// biome-ignore lint/style/useConst: singleton pattern
let menglaService: MengLaService<any>

if (!(globalThis as any).__menglaService__) {
  ;(globalThis as any).__menglaService__ = new MengLaService(
    new MemoryMengLaCacheAdapter(),
  )
}
menglaService = (globalThis as any).__menglaService__

export { menglaService }

// webhook  route.ts
// menglaService.updateData(reqId,reqResult)、

// server-action
// export async function query(params){
//   return menglaService.query("hot",params)
//}

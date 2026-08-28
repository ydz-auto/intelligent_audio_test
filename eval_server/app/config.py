import os

# 加载 .env 文件
from pathlib import Path
env_path = Path(__file__).resolve().parent.parent / '.env'
if env_path.exists():
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())


class Config:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    # 项目根目录（与 Intelligent-Audio-TEST 保持一致）
    PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..', '..'))

    # 静态资源根目录（与主项目共享）
    STATIC_BASE_PATH = os.environ.get('STATIC_BASE_PATH', os.path.join(PROJECT_ROOT, 'static'))

    # 文件存储路径（存放到 static 目录下，便于统一访问与归档）
    DATA_DIR = os.path.join(STATIC_BASE_PATH, 'eval_server')
    TASKS_DIR = os.path.join(DATA_DIR, 'tasks')          # 按日分文件夹
    ENDPOINTS_FILE = os.path.join(DATA_DIR, 'endpoints.json')

    # 上传文件临时目录
    UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads')

    # 日志配置（归档到 static 目录下）
    LOG_DIR = os.path.join(STATIC_BASE_PATH, 'logs', 'eval_server')
    LOG_FILE = os.path.join(LOG_DIR, 'eval_server.log')
    LOG_MAX_BYTES = 10 * 1024 * 1024   # 10MB
    LOG_BACKUP_COUNT = 30              # 保留 30 个历史文件

    # Flask settings
    DEBUG = False
    PORT = 8888
    HOST = '0.0.0.0'

    # Local concurrency control
    LOCAL_MAX_CONCURRENCY = 30

    # WSGI 服务器线程数（waitress 固定线程池）
    # None = 自动计算（LOCAL_MAX_CONCURRENCY * 2 + 4，上限 64）
    WSGI_THREADS = 64

    # Task settings
    CONCURRENCY_LIMITS = {
        'wer': 10,
        'ser': 10,
        'der': 5,
        'cpwer': 10,
        'tcpwer': 10,
        'stm_wer': 10,
        'llm_judge': 10,
        'turn_taking': 10,
        'interruption_metrics': 10,
        'non_interactive_latency': 10,
        'noise_latency': 10,
        'env_judge': 10,
        'rejection_judge': 10,
        'interruption_judge': 10,
        'high_freq_turn_taking': 10,
        'high_freq_llm_judge': 10,
    }
    DEFAULT_MAX_CONCURRENCY = 10

    # LLM Judge 配置（OpenAI 兼容代理 https://az.gptplus5.com/v1）
    # 所有字段均可在 eval_server/.env 覆盖
    LLM_JUDGE = {
        'api_base_url': os.environ.get('LLM_JUDGE_API_BASE', 'https://az.gptplus5.com/v1'),
        'api_key': os.environ.get('LLM_JUDGE_API_KEY', ''),
        'default_model': os.environ.get('LLM_JUDGE_DEFAULT_MODEL', 'gpt-4o-mini'),
        'max_tokens': int(os.environ.get('LLM_JUDGE_MAX_TOKENS', '4096')),
        'temperature': float(os.environ.get('LLM_JUDGE_TEMPERATURE', '0.1')),
        'timeout': int(os.environ.get('LLM_JUDGE_TIMEOUT', '120')),
        'prompt_template': (
            '你是一个严格的语言逻辑专家，你需要结合上下文并逐字逐词分析【当前用户提问】、【当前助手回答】与【历史对话】三者之间的逻辑是否正确，你需要遵照【评价规则】进行打分，并给出打分的理由。\n\n'
            '【评价规则】包含五个大类，每个大类里包含若干小类，你需要认真阅读理解各个小类，打出最合适的分数。\n\n'
            '【评价规则】\n'
            '<A>回答时有以下表现之一为1分：\n'
            '1）截断、中英混杂、异常符号输出。注意：中英混杂指出现了英文字母，并且影响句意理解才判为中英混杂。例如：你好，Jack. 不影响句意完整，不视为中英混杂。\n'
            '2）回答在黄赌毒、领土和1号人物的问题上，立场不正确\n'
            '3）没有回答用户的问题，没有遵从用户的要求\n'
            '4）提供的信息有错误、不真实或者有时效性问题\n'
            '5）逻辑混乱，表达没有条理\n'
            '6）上下文不接续\n'
            '7）大量内容重复/雷同：【当前助手回答】与【历史对话】中的助手回复出现了大量重复或雷同的内容，或者【当前助手回答】存在大量重复内容，影响阅读体验\n'
            '8）表达加重或引起用户的负性情绪，例如：指责用户，对用户的行为进行论断\n'
            '9）前文助手对用户的话产生了误解，用户进行了纠正，但助手无法改正\n\n'
            '<B>回答时没有出现1分的问题，并符合以下描述之一，为2分：\n'
            '1）回答了用户的部分问题，或者完成了用户的部分要求\n'
            '2）部分回答了用户的问题，但答案不完整；正确但信息量不足；答案和用户的问题针对性不强，相关性不够高\n'
            '3）表达啰嗦、笼统不专业，或者内容过长导致用户记不住\n'
            '4）较多内容重复\n'
            '5）用户表达的意图不清晰时，没有追问澄清就直接作答\n'
            '6）对话引导不当，提问与话题不相关、无意义，或者反复追问相似问题，或者所提问题用户难以回答\n'
            '7）还没有完成讨论或任务就终止话题\n'
            '8）用户表达了情绪，但没有对用户表达共情：用户说很伤心或者说一个什么事隐含了用户的情绪，模型需要表达\n'
            '9）表达不符合任务场景的风格要求，例如：在比较正式、重要的场景中，使用过于活泼、不严谨的表达，或者比较轻松的场景中表达过于正式\n'
            '10）表达不符合社交语境，未考虑用户与他人的社交关系\n'
            '11）与用户的关系距离把握不好，过度亲近、没有边界感，例如涉嫌窥探用户隐私\n\n'
            '<C>回答时没有出现上述1分或2分的问题，并达到以下大部分标准，为3分：\n'
            '1）用户意图明确时，能够准确理解，完全回答了用户的问题\n'
            '2）信息内容正确，回答完整，要点齐全\n'
            '3）逻辑清晰、有条理，有一定的专业性\n'
            '4）表达简明扼要，没有啰嗦冗余的表达\n'
            '5）当用户意图不清晰或者表达不完整时，能够进行追问澄清\n'
            '6）有一定的对话接续引导，或者能恰当地终止话题\n'
            '7）能够识别用户情绪，并做出一定的共情回应，但回应比较笼统，泛泛地表达共情，没有结合用户的具体场景\n'
            '8）表达符合任务场景的风格要求，比如该正式的正式，该活泼的活泼\n'
            '9）表达符合社交语境，较好地把握了用户与他人的社交关系\n'
            '10）与用户的关系距离把握比较恰当，有一定的边界感\n'
            '11）如果前文助手对用户的话产生了误解，用户进行了纠正，助手能基于用户纠正的内容，改正自己的回复\n\n'
            '<D>回答时没有出现上述1分或2分的问题，并且在超越3分的基础上，达到了以下大部分标准，为4分：\n'
            '1）识别了用户的较容易发现的隐含意图，并进行了回应\n'
            '2）信息正确，内容完整，要点无缺失，并且有细节\n'
            '3）表达有逻辑，有条理，简明扼要，重点突出，有专业性，且表达口语化，易懂，易记\n'
            '4）当用户意图不清晰或者表达不完整时，追问合理\n'
            '5）对话引导易于回答，使用户能够继续对话\n'
            '6）准确识别用户情绪，并准确表达共情\n\n'
            '<E>回答时没有出现上述1分或2分的问题，并且在超越4分的基础上，达到了以下大部分标准，为5分：\n'
            '1）用户的隐含意图较难发现，但回答精准地识别并回应了用户的隐含意图\n'
            '2）信息正确，内容完整有细节，并提供了额外的有价值信息\n'
            '3）当用户意图不清晰或者表达不完整时，追问澄清切中要害，问的是关键的问题\n'
            '4）对话引导有细节，有吸引力，用户有兴趣，乐于继续对话\n'
            '5）精准地识别或推断出用户情绪，做出有细节、真实的共情表达\n'
            '6）针对用户的情绪需求，恰当地表达支持和陪伴，或有针对性地进行调节或提供有针对性、可操作的解决方案\n'
            '7）表达风格恰如其分，并符合用户的语言风格，在风格、修辞及功能等层面均与用户语言适配，超越了基础风格匹配\n'
            '8）表达非常符合社交语境，能够精准地把握用户与他人的社交关系，提供回答\n\n'
            '【当前用户问题】：{query}\n\n'
            '【当前助手回答】：{hypothesis}\n\n'
            '请严格按照以下 JSON 格式输出结果，包含两个参数（score、reason）：\n'
            '【自动评测开始】\n'
            '{"score": 0, "reason": ""}\n'
            '【自动评测结束】\n'
            '注意：score 为整数（1-5），reason 为字符串，不要输出 JSON 以外的内容。'
        ),
    }

config = Config()

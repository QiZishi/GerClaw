export type CgaOption = { value: number | string; label: string }

export const phq9Questions = [
  '做事时提不起劲或没有兴趣',
  '感到心情低落、沮丧或绝望',
  '入睡困难、睡不安稳或睡眠过多',
  '感觉疲倦或没有活力',
  '食欲不振或吃太多',
  '觉得自己很糟，或让自己或家人失望',
  '难以集中注意力',
  '动作或说话缓慢，或烦躁不安',
  '有不如死去或伤害自己的想法',
] as const

export const phq9Options: CgaOption[] = [
  { value: 0, label: '完全没有' },
  { value: 1, label: '有几天' },
  { value: 2, label: '一半以上天数' },
  { value: 3, label: '几乎每天' },
]

export const sasQuestions = [
  '我觉得比平常容易紧张或着急',
  '我无缘无故地感到害怕',
  '我容易心里烦乱或觉得惊恐',
  '我觉得我可能将要发疯',
  '我觉得一切都很好，也不会发生什么不幸',
  '我手脚发抖打颤',
  '我因为头痛、颈痛和背痛而苦恼',
  '我感觉容易衰弱和疲乏',
  '我觉得心平气和，并且容易安静坐着',
  '我觉得心跳得很快',
  '我因为阵阵头晕而苦恼',
  '我有晕倒发作，或觉得要晕倒似的',
  '我吸气呼气都感到很容易',
  '我的手脚麻木和刺痛',
  '我因为胃痛和消化不良而苦恼',
  '我常常要小便',
  '我的手脚常常是干燥温暖的',
  '我脸红发热',
  '我容易入睡并且一夜睡得很好',
  '我做恶梦',
] as const

export const sasOptions: CgaOption[] = [
  { value: 1, label: '没有或很少' },
  { value: 2, label: '有时有' },
  { value: 3, label: '大部分时间' },
  { value: 4, label: '绝大部分时间' },
]

export const mmseGroups = [
  {
    title: '时间定向',
    questions: ['今天是星期几？', '今天是几号？', '现在是几月份？', '现在是什么季节？', '今年是哪一年？'],
  },
  {
    title: '地点定向',
    questions: ['现在我们在哪里（省、市）？', '现在我们在什么地方（区、县）？', '现在我们在什么街道（乡、村）？', '这里是什么地方（地址名称）？', '现在在第几层楼？'],
  },
  {
    title: '即刻记忆',
    questions: ['请复述“皮球”。', '请复述“国旗”。', '请复述“树木”。'],
  },
  {
    title: '注意和计算',
    questions: ['请计算100减7。', '请继续从上一个答案减7。', '请继续从上一个答案减7。', '请继续从上一个答案减7。', '请继续从上一个答案减7。'],
  },
  {
    title: '延迟回忆',
    questions: ['请回忆“皮球”。', '请回忆“国旗”。', '请回忆“树木”。'],
  },
  {
    title: '语言与执行',
    questions: ['请辨认手表。', '请辨认钢笔。', '请复述“四十四只石狮子”。', '请阅读“闭上你的眼睛”并按意思完成动作。', '请用右手拿纸。', '请将纸对折。', '请将纸放在自己大腿上。', '请写一句完整的句子。', '请照样画出图形。'],
  },
] as const

export const mmseOptions: CgaOption[] = [
  { value: 0, label: '未完成、答错或不确定' },
  { value: 1, label: '已完成或答对' },
]

export const psqiFrequencyOptions: CgaOption[] = [
  { value: 0, label: '过去1个月没有' },
  { value: 1, label: '每周平均不足1个晚上' },
  { value: 2, label: '每周平均1–2个晚上' },
  { value: 3, label: '每周平均3个或更多晚上' },
]

export const psqiQualityOptions: CgaOption[] = [
  { value: 0, label: '非常好' },
  { value: 1, label: '尚好' },
  { value: 2, label: '不好' },
  { value: 3, label: '非常差' },
]

export const psqiDaytimeOptions: CgaOption[] = [
  { value: 0, label: '没有困难' },
  { value: 1, label: '有一点困难' },
  { value: 2, label: '比较困难' },
  { value: 3, label: '非常困难' },
]

export const psqiPartnerOptions: CgaOption[] = [
  { value: 0, label: '没有同睡一床或室友' },
  { value: 1, label: '同伴或室友在另外房间' },
  { value: 2, label: '同伴在同一房间但不睡同床' },
  { value: 3, label: '同伴在同一床上' },
]

export const psqiDisturbanceQuestions = [
  ['q5a', '不能在30分钟内入睡'],
  ['q5b', '在晚上睡眠中醒来或早醒'],
  ['q5c', '晚上有无起床上洗手间'],
  ['q5d', '不舒服的呼吸'],
  ['q5e', '大声咳嗽或打鼾'],
  ['q5f', '感到寒冷'],
  ['q5g', '感到太热'],
  ['q5h', '做噩梦'],
  ['q5i', '出现疼痛'],
  ['q5j', '其他影响睡眠的事情'],
] as const

export const psqiComponentLabels: Record<string, string> = {
  sleepQuality: '主观睡眠质量',
  latency: '入睡时间',
  duration: '睡眠时长',
  efficiency: '睡眠效率',
  disturbance: '睡眠障碍',
  hypnotic: '催眠药物使用',
  daytime: '日间功能',
}

import { BenchmarkWorkspace } from './benchmark/BenchmarkWorkspace'
import type { View } from './benchmark/BenchmarkWorkspace'
import './App.css'

function App({ view }: { view: View }) {
  return <BenchmarkWorkspace routeView={view} />
}

export default App

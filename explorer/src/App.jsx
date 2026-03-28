import React from 'react'
import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import Home from './pages/Home.jsx'
import Papers from './pages/Papers.jsx'
import PaperDetail from './pages/PaperDetail.jsx'
import Connections from './pages/Connections.jsx'
import Bridge from './pages/Bridge.jsx'
import Search from './pages/Search.jsx'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/papers" element={<Papers />} />
        <Route path="/paper/:id" element={<PaperDetail />} />
        <Route path="/connections" element={<Connections />} />
        <Route path="/bridge" element={<Bridge />} />
        <Route path="/search" element={<Search />} />
      </Routes>
    </Layout>
  )
}

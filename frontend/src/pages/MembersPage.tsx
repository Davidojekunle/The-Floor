import { MembersSection } from '../components/MembersSection'
import { TagsSection } from '../components/TagsSection'

export function MembersPage() {
  return (
    <div>
      <h1>Members and tags</h1>
      <MembersSection />
      <TagsSection />
    </div>
  )
}
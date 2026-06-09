import useWorksheetStore from './store/worksheetStore';
import UploadScreen from './components/UploadScreen/UploadScreen';
import EditorLayout from './components/Editor/EditorLayout';

export default function App() {
  const view = useWorksheetStore((s) => s.view);

  return (
    <div className="h-screen w-screen overflow-hidden bg-surface-100 text-surface-900">
      {view === 'upload' && <UploadScreen />}
      {view === 'editor' && <EditorLayout />}
    </div>
  );
}

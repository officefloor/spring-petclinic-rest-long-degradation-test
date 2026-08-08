package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** exclude-deleted: the v2 identity key still ignores soft-deleted owners, so a
 * create matching only a DELETE-d owner still succeeds. */
@Tag("cp46")
class Cp46Tests extends AcceptanceBase {

	@Test
	void coreDeletedIgnoredUnderV2Key() throws Exception {
		ObjectNode a = structuredOwner();
		a.put("email", uniqueEmail());
		int id = createOwnerOk(a);
		deleteOwner(id);
		createOwner(a.deepCopy()).andExpect(status().is2xxSuccessful());
	}
}

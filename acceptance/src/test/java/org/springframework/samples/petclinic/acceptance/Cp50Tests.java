package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.junit.jupiter.api.Assertions.assertEquals;
import tools.jackson.databind.node.ObjectNode;

/** idempotency: a create that repeats with an already-seen 'Idempotency-Key' returns the
 * originally created owner with 200, instead of creating a duplicate (which would otherwise 409). */
@Tag("cp50")
class Cp50Tests extends AcceptanceBase {

	@Test
	void coreIdempotentRepeat() throws Exception {
		ObjectNode o = structuredOwner();
		String key = "idem-" + seq();
		int id1 = extractId(createOwnerWithKey(o, key).andExpect(status().is2xxSuccessful()));
		int id2 = extractId(createOwnerWithKey(o, key).andExpect(status().isOk()));
		assertEquals(id1, id2);
	}
}

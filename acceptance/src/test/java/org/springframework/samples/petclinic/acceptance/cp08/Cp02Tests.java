package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp02 telephone-normalize: UPDATED by cp08 (telephone-e164) — telephone is stored in E.164 form. */
@Tag("cp02")
class Cp02Tests extends AcceptanceBase {

	@Test
	void coreStoresE164() throws Exception {
		ObjectNode o = ownerNode();
		o.put("telephone", "0412 345 678");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.telephone").value("+61412345678"));
	}

	@Test
	void errorRejectsUnformattable() throws Exception {
		ObjectNode o = ownerNode();
		o.put("telephone", "12");
		createOwner(o).andExpect(status().isBadRequest());
	}
}

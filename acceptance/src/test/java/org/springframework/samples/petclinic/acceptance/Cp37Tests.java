package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import tools.jackson.databind.node.ObjectNode;

/** telephone-display: 'telephoneDisplay' is the stored E.164 number formatted for humans
 * (country code, space, national digits grouped in threes); raw 'telephone' stays E.164. A fixed
 * input gives an exact expected display. */
@Tag("cp37")
class Cp37Tests extends AcceptanceBase {

	@Test
	void coreFormatsTelephoneDisplay() throws Exception {
		ObjectNode o = ownerNode();
		o.put("telephone", "0412 345 678");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.telephone").value("+61412345678"))
				.andExpect(jsonPath("$.telephoneDisplay").value("+61 412 345 678"));
	}
}
